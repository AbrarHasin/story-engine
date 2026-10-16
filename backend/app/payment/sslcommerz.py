"""
SSLCommerz payment integration.
Docs: https://sslcommerz.com/integration-document/
Sandbox: https://developer.sslcommerz.com
"""
import hashlib
import hmac
import uuid
import aiohttp
import logging
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.db import Payment, PaymentStatus, PlanTier, User, utcnow
from app.models.schemas import PaymentInitiateRequest, PaymentInitiateResponse, PLAN_PRICES_BDT

router = APIRouter(prefix="/payment", tags=["Payment"])
logger = logging.getLogger(__name__)

SSLCOMMERZ_SANDBOX_URL = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
SSLCOMMERZ_LIVE_URL    = "https://securepay.sslcommerz.com/gwprocess/v4/api.php"
SSLCOMMERZ_SANDBOX_VALIDATE_URL = "https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php"
SSLCOMMERZ_LIVE_VALIDATE_URL    = "https://securepay.sslcommerz.com/validator/api/validationserverAPI.php"


def _gateway_url() -> str:
    return SSLCOMMERZ_SANDBOX_URL if settings.SSLCOMMERZ_SANDBOX else SSLCOMMERZ_LIVE_URL


def _validate_url() -> str:
    return SSLCOMMERZ_SANDBOX_VALIDATE_URL if settings.SSLCOMMERZ_SANDBOX else SSLCOMMERZ_LIVE_VALIDATE_URL


async def _create_gateway_session(payload: dict) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(_gateway_url(), data=payload) as resp:
            return await resp.json(content_type=None)


async def _validate_with_gateway(val_id: str) -> dict:
    """Ask SSLCommerz to confirm a val_id (server-to-server)."""
    params = {
        "val_id":       val_id,
        "store_id":     settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASS,
        "format":       "json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(_validate_url(), params=params) as resp:
            return await resp.json(content_type=None)


def _signature_valid(data: dict) -> bool:
    """Verify the IPN verify_sign (MD5 over the fields named in verify_key)."""
    verify_sign = data.get("verify_sign")
    verify_key = data.get("verify_key")
    if not verify_sign or not verify_key or not settings.SSLCOMMERZ_STORE_PASS:
        return False
    params = {}
    for k in str(verify_key).split(","):
        if k == "store_passwd":
            params[k] = hashlib.md5(settings.SSLCOMMERZ_STORE_PASS.encode()).hexdigest()
        elif k in data:
            params[k] = data[k]
        else:
            return False
    signed = "&".join(f"{k}={params[k]}" for k in sorted(params))
    expected = hashlib.md5(signed.encode()).hexdigest()
    return hmac.compare_digest(expected, str(verify_sign).lower())


@router.post(
    "/initiate",
    response_model=PaymentInitiateResponse,
    summary="Initiate SSLCommerz payment session",
)
async def initiate_payment(
    body: PaymentInitiateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    backend_base = settings.BACKEND_PUBLIC_URL.rstrip("/")

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
        "cus_name":       user.name or "Story Engine User",
        "cus_email":      user.email,
        "cus_add1":       "Dhaka",
        "cus_city":       "Dhaka",
        "cus_country":    "Bangladesh",
        "cus_phone":      "01700000000",
        "ship_name":      user.name or "Story Engine User",
        "ship_add1":      "Dhaka",
        "ship_city":      "Dhaka",
        "ship_country":   "Bangladesh",
        "shipping_method": "NO",
        "num_of_item":    1,
        "emi_option":     0,
    }

    # Record payment initiation in DB
    payment = Payment(
        user_id=user.id,
        tran_id=tran_id,
        amount=amount,
        plan=body.plan,
        status=PaymentStatus.initiated,
    )
    db.add(payment)
    await db.commit()

    data = await _create_gateway_session(payload)

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
    Requires a valid MD5 signature, confirms with the gateway validation API,
    then upgrades the user plan. CONFIRMED is terminal.
    """
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}

    tran_id = data.get("tran_id")
    val_id  = data.get("val_id")
    status  = data.get("status")

    if not _signature_valid(data):
        logger.warning("IPN signature missing or mismatched for tran_id=%s", tran_id)
        raise HTTPException(400, "Invalid signature")

    result = await db.execute(select(Payment).where(Payment.tran_id == tran_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "Payment not found")

    # CONFIRMED is terminal: later IPNs (duplicates, late FAILED) change nothing.
    if payment.status == PaymentStatus.confirmed:
        return {"status": "received"}

    confirmed = False
    if status in ("VALID", "VALIDATED") and val_id:
        v = await _validate_with_gateway(val_id)
        try:
            confirmed = (
                v.get("status") in ("VALID", "VALIDATED")
                and v.get("tran_id") == payment.tran_id
                and v.get("currency", "BDT") == "BDT"
                and abs(float(v.get("amount", 0)) - payment.amount) < 1
            )
        except (TypeError, ValueError):
            confirmed = False

    if confirmed:
        payment.status       = PaymentStatus.confirmed
        payment.val_id       = str(val_id)
        payment.ipn_payload  = data
        payment.confirmed_at = utcnow()

        user = await db.get(User, payment.user_id)
        if user:
            user.plan = payment.plan

        await db.commit()
        logger.info("Payment confirmed: tran_id=%s plan=%s", tran_id, payment.plan)
    else:
        payment.status = PaymentStatus.failed
        await db.commit()

    return {"status": "received"}

async def _return_to_frontend(request: Request, outcome: str) -> RedirectResponse:
    """
    Send the browser back to the SPA at /billing/{outcome}.
    SSLCommerz POSTs a form to these URLs (GET is kept for manual testing).
    Nothing is trusted or changed here: only the signed IPN upgrades a plan.
    """
    tran_id = request.query_params.get("tran_id")
    if not tran_id and request.method == "POST":
        tran_id = (await request.form()).get("tran_id")  # type: ignore[assignment]
    url = f"{settings.FRONTEND_URL.rstrip('/')}/billing/{outcome}"
    if isinstance(tran_id, str) and tran_id:
        url += "?" + urlencode({"tran_id": tran_id})
    return RedirectResponse(url, status_code=303)


@router.api_route("/success", methods=["GET", "POST"], summary="SSLCommerz success redirect")
async def payment_success(request: Request):
    return await _return_to_frontend(request, "success")


@router.api_route("/fail", methods=["GET", "POST"], summary="SSLCommerz fail redirect")
async def payment_fail(request: Request):
    return await _return_to_frontend(request, "fail")


@router.api_route("/cancel", methods=["GET", "POST"], summary="SSLCommerz cancel redirect")
async def payment_cancel(request: Request):
    return await _return_to_frontend(request, "cancel")
