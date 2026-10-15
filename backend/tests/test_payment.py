"""
Payment integrity tests (SSLCommerz). Hit the live DB; the gateway is mocked.
"""
import hashlib
import uuid

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.core.auth import DEV_USER_ID, create_access_token
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.db import Payment, PaymentStatus, PlanTier, User
from app.payment import sslcommerz

STORE_PASS = "test-store-pass"


@pytest.fixture(autouse=True)
def _gateway_settings(monkeypatch):
    monkeypatch.setattr(settings, "SSLCOMMERZ_STORE_ID", "teststore")
    monkeypatch.setattr(settings, "SSLCOMMERZ_STORE_PASS", STORE_PASS)
    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "https://api.example.test")


@pytest.fixture
async def anon(dev_user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def other_user():
    uid = uuid.uuid4()
    async with SessionLocal() as s:
        s.add(User(id=uid, email=f"{uid}@example.test", name="Other", plan=PlanTier.free))
        await s.commit()
    yield uid


def _auth(uid, email="x@example.test"):
    return {"Authorization": f"Bearer {create_access_token(uid, email)}"}


def _sign(data: dict) -> dict:
    """Return data with verify_key/verify_sign built the way SSLCommerz does."""
    data = dict(data)
    keys = sorted(data.keys()) + ["store_passwd"]
    data["verify_key"] = ",".join(keys)
    params = dict(data)
    params["store_passwd"] = hashlib.md5(STORE_PASS.encode()).hexdigest()
    s = "&".join(f"{k}={params[k]}" for k in sorted(keys))
    data["verify_sign"] = hashlib.md5(s.encode()).hexdigest()
    return data


async def _make_payment(user_id, status=PaymentStatus.initiated, amount=499.0):
    tran_id = f"SE-{uuid.uuid4().hex[:16].upper()}"
    async with SessionLocal() as s:
        s.add(Payment(user_id=user_id, tran_id=tran_id, amount=amount,
                      plan=PlanTier.pro, status=status))
        await s.commit()
    return tran_id


async def _get(tran_id) -> Payment:
    async with SessionLocal() as s:
        return (await s.execute(select(Payment).where(Payment.tran_id == tran_id))).scalar_one()


async def _plan(uid) -> PlanTier:
    async with SessionLocal() as s:
        return (await s.get(User, uid)).plan


@pytest.fixture
def gateway(monkeypatch):
    """Mock gateway. Tests set .session_response / .validation_response."""
    class G:
        session_response = {"status": "SUCCESS", "GatewayPageURL": "https://pay.example.test/x"}
        validation_response = None
        payloads: list = []
        validated: list = []

    g = G()
    g.payloads, g.validated = [], []

    async def fake_session(payload):
        g.payloads.append(payload)
        return g.session_response

    async def fake_validate(val_id):
        g.validated.append(val_id)
        return g.validation_response or {"status": "VALID"}

    monkeypatch.setattr(sslcommerz, "_create_gateway_session", fake_session)
    monkeypatch.setattr(sslcommerz, "_validate_with_gateway", fake_validate)
    return g


# ── initiate ────────────────────────────────────────────────────────────────

async def test_initiate_requires_auth(anon, monkeypatch, gateway):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "real-secret")
    r = await anon.post("/api/v1/payment/initiate", json={"plan": "pro"})
    assert r.status_code == 401
    assert gateway.payloads == []


async def test_initiate_credits_authenticated_user(anon, other_user, gateway):
    r = await anon.post("/api/v1/payment/initiate", json={"plan": "pro"},
                        headers=_auth(other_user))
    assert r.status_code == 200, r.text
    p = await _get(r.json()["tran_id"])
    assert p.user_id == other_user
    assert p.user_id != DEV_USER_ID


async def test_initiate_uses_backend_public_url(anon, other_user, gateway):
    r = await anon.post("/api/v1/payment/initiate", json={"plan": "pro"},
                        headers=_auth(other_user))
    assert r.status_code == 200
    payload = gateway.payloads[0]
    for k in ("success_url", "fail_url", "cancel_url", "ipn_url"):
        assert payload[k].startswith("https://api.example.test/api/v1/payment/")


# ── IPN signature ───────────────────────────────────────────────────────────

async def test_ipn_rejects_missing_signature(anon, other_user, gateway):
    tran_id = await _make_payment(other_user)
    r = await anon.post("/api/v1/payment/ipn", data={
        "tran_id": tran_id, "val_id": "v1", "status": "VALID", "amount": "499.00"})
    assert r.status_code == 400
    assert (await _get(tran_id)).status == PaymentStatus.initiated
    assert await _plan(other_user) == PlanTier.free


async def test_ipn_rejects_bad_signature(anon, other_user, gateway):
    tran_id = await _make_payment(other_user)
    data = _sign({"tran_id": tran_id, "val_id": "v1", "status": "VALID", "amount": "499.00"})
    data["verify_sign"] = "0" * 32
    r = await anon.post("/api/v1/payment/ipn", data=data)
    assert r.status_code == 400
    assert (await _get(tran_id)).status == PaymentStatus.initiated
    assert gateway.validated == []


async def test_ipn_valid_signature_confirms_and_upgrades(anon, other_user, gateway):
    tran_id = await _make_payment(other_user)
    gateway.validation_response = {"status": "VALID", "tran_id": tran_id,
                                   "amount": "499.00", "currency": "BDT"}
    data = _sign({"tran_id": tran_id, "val_id": "v1", "status": "VALID", "amount": "499.00"})
    r = await anon.post("/api/v1/payment/ipn", data=data)
    assert r.status_code == 200, r.text
    assert (await _get(tran_id)).status == PaymentStatus.confirmed
    assert await _plan(other_user) == PlanTier.pro


# ── gateway validation API ──────────────────────────────────────────────────

async def test_ipn_calls_validation_api(anon, other_user, gateway):
    tran_id = await _make_payment(other_user)
    gateway.validation_response = {"status": "VALIDATED", "tran_id": tran_id,
                                   "amount": "499.00", "currency": "BDT"}
    data = _sign({"tran_id": tran_id, "val_id": "val-123", "status": "VALID", "amount": "499.00"})
    await anon.post("/api/v1/payment/ipn", data=data)
    assert gateway.validated == ["val-123"]


@pytest.mark.parametrize("resp", [
    {"status": "INVALID_TRANSACTION"},
    {"status": "VALID", "tran_id": "OTHER", "amount": "499.00", "currency": "BDT"},
    {"status": "VALID", "amount": "1.00", "currency": "BDT"},
    {"status": "VALID", "amount": "499.00", "currency": "USD"},
])
async def test_ipn_not_confirmed_when_validation_fails(anon, other_user, gateway, resp):
    tran_id = await _make_payment(other_user)
    resp = dict(resp)
    resp.setdefault("tran_id", tran_id)
    gateway.validation_response = resp
    data = _sign({"tran_id": tran_id, "val_id": "v1", "status": "VALID", "amount": "499.00"})
    r = await anon.post("/api/v1/payment/ipn", data=data)
    assert r.status_code == 200
    assert (await _get(tran_id)).status != PaymentStatus.confirmed
    assert await _plan(other_user) == PlanTier.free


# ── CONFIRMED is terminal ───────────────────────────────────────────────────

async def test_late_failed_ipn_cannot_overwrite_confirmed(anon, other_user, gateway):
    tran_id = await _make_payment(other_user, status=PaymentStatus.confirmed)
    data = _sign({"tran_id": tran_id, "val_id": "v1", "status": "FAILED", "amount": "499.00"})
    r = await anon.post("/api/v1/payment/ipn", data=data)
    assert r.status_code == 200
    assert (await _get(tran_id)).status == PaymentStatus.confirmed
