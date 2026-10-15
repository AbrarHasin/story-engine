"""
SSLCommerz payment integration.
Docs: https://sslcommerz.com/integration-document/
Sandbox: https://developer.sslcommerz.com
"""
import hashlib
import uuid
import aiohttp
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.db import Payment, PaymentStatus, PlanTier, User
from app.models.schemas import PaymentInitiateRequest, PaymentInitiateResponse, PLAN_PRICES_BDT

router = APIRouter(prefix="/payment", tags=["Payment"])
logger = logging.getLogger(__name__)

SSLCOMMERZ_SANDBOX_URL = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
SSLCOMMERZ_LIVE_URL    = "https://securepay.sslcommerz.com/gwprocess/v4/api.php"

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _gateway_url() -> str:
    return SSLCOMMERZ_SANDBOX_URL if settings.SSLCOMMERZ_SANDBOX else SSLCOMMERZ_LIVE_URL


@router.post(
    "/initiate",
    response_model=PaymentInitiateResponse,
    summary="Initiate SSLCommerz payment session",
)
async def initiate_payment(
    body: PaymentInitiateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a payment session with SSLCommerz and return the payment URL.
    Redirect the user to `payment_url` to complete payment.

    Plans:
    - pro        → BDT 499/month
    - enterprise → BDT 1,499/month
    """
    if body.plan == PlanTier.free:
        raise HTTPException(400, "Free plan requires no payment")

    amount = PLAN_PRICES_BDT[body.plan]
    tran_id = f"SE-{uuid.uuid4().hex[:16].upper()}"
    backend_base = settings.FRONTEND_URL.replace("5173", "8000")  # crude, improve with setting

    payload = {
        "store_id":       settings.SSLCOMMERZ_STORE_ID,
        "store_passwd":   settings.SSLCOMMERZ_STORE_PASS,
        "total_amount":   amount,
        "currency":       "BDT",
        "tran_id":        tran_id,
        "success_url":    f"{backend_base}/api/v1/payment/success",
        "fail_url":       f"{backend_base}/api/v1/payment/fail",
        "cancel_url":     f"{backend_base}/api/v1/payment/cancel",
        "ipn_url":        f"{backend_base}/api/v1/payment/ipn",
        "product_name":   f"Story Engine {body.plan.value.title()} Plan",
        "product_category": "subscription",
        "product_profile": "general",
        "cus_name":       "Story Engine User",
        "cus_email":      "user@example.com",
        "cus_add1":       "Dhaka",
        "cus_city":       "Dhaka",
        "cus_country":    "Bangladesh",
        "cus_phone":      "01700000000",
        "ship_name":      "Story Engine User",
        "ship_add1":      "Dhaka",
        "ship_city":      "Dhaka",
        "ship_country":   "Bangladesh",
        "shipping_method": "NO",
        "num_of_item":    1,
        "emi_option":     0,
    }

    # Record payment initiation in DB
    payment = Payment(
        user_id=DEV_USER_ID,
        tran_id=tran_id,
        amount=amount,
        plan=body.plan,
        status=PaymentStatus.initiated,
    )
    db.add(payment)
    await db.commit()

    async with aiohttp.ClientSession() as session:
        async with session.post(_gateway_url(), data=payload) as resp:
            data = await resp.json(content_type=None)

    if data.get("status") != "SUCCESS":
        raise HTTPException(502, f"SSLCommerz error: {data.get('failedreason', 'unknown')}")

    return PaymentInitiateResponse(
        payment_url=data["GatewayPageURL"],
        tran_id=tran_id,
        amount=amount,
    )


@router.post("/ipn", summary="SSLCommerz IPN webhook (async payment confirmation)")
async def payment_ipn(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receives async payment notification from SSLCommerz.
    Validates MD5 hash, then upgrades user plan.
    """
    form = await request.form()
    data = dict(form)

    tran_id   = data.get("tran_id")
    val_id    = data.get("val_id")
    status    = data.get("status")
    amount    = float(str(data.get("amount", 0)))
    verify_key= data.get("verify_sign")
    verify_str= data.get("verify_key")

    # Validate MD5 signature
    if verify_key and verify_str:
        params = {k: v for k, v in data.items() if k not in ("verify_sign", "verify_sign_sha2")}
        params["store_passwd"] = hashlib.md5(settings.SSLCOMMERZ_STORE_PASS.encode()).hexdigest()
        sorted_str = "&".join(f"{k}={params[k]}" for k in sorted(params))
        expected = hashlib.md5(sorted_str.encode()).hexdigest()
        if expected != verify_key:
            logger.warning("IPN signature mismatch for tran_id=%s", tran_id)
            raise HTTPException(400, "Signature mismatch")

    result = await db.execute(select(Payment).where(Payment.tran_id == tran_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "Payment not found")

    if status == "VALID" and abs(amount - payment.amount) < 1:
        payment.status       = PaymentStatus.confirmed
        payment.val_id       = str(val_id) if val_id else None
        payment.ipn_payload  = data
        payment.confirmed_at = datetime.utcnow()

        # Upgrade user plan
        user = await db.get(User, payment.user_id)
        if user:
            user.plan = payment.plan

        await db.commit()
        logger.info("Payment confirmed: tran_id=%s plan=%s", tran_id, payment.plan)
    else:
        payment.status = PaymentStatus.failed
        await db.commit()

    return {"status": "received"}


@router.get("/success", summary="SSLCommerz success redirect")
async def payment_success(tran_id: str):
    return {"message": "Payment successful", "tran_id": tran_id,
            "redirect": f"{settings.FRONTEND_URL}/billing/success?tran_id={tran_id}"}


@router.get("/fail", summary="SSLCommerz fail redirect")
async def payment_fail(tran_id: str):
    return {"message": "Payment failed", "tran_id": tran_id}


@router.get("/cancel", summary="SSLCommerz cancel redirect")
async def payment_cancel(tran_id: str):
    return {"message": "Payment cancelled", "tran_id": tran_id}
