"""Billing follow-ups: plan catalogue, payment status, month-aware /auth/me. Live DB, no gateway calls."""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import limits
from app.core.auth import create_access_token
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.db import Payment, PaymentStatus, PlanTier, User


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _user(plan=PlanTier.free, count=0, period=None) -> uuid.UUID:
    uid = uuid.uuid4()
    async with SessionLocal() as s:
        s.add(User(id=uid, email=f"{uid}@example.test", name="U", plan=plan,
                   stories_this_month=count, quota_period_start=period))
        await s.commit()
    return uid


def _auth(uid):
    return {"Authorization": f"Bearer {create_access_token(uid, f'{uid}@example.test')}"}


async def _payment(uid, status=PaymentStatus.initiated) -> str:
    tran_id = f"SE-{uuid.uuid4().hex[:16].upper()}"
    async with SessionLocal() as s:
        s.add(Payment(user_id=uid, tran_id=tran_id, amount=499.0, plan=PlanTier.pro, status=status))
        await s.commit()
    return tran_id


# -- GET /payment/plans --------------------------------------------------------

async def test_plans_come_from_settings(client, monkeypatch):
    monkeypatch.setattr(settings, "PLAN_LIMIT_PRO", 321)
    monkeypatch.setattr(settings, "PLAN_PRICE_PRO_BDT", 555.0)
    r = await client.get("/api/v1/payment/plans")
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "BDT"
    plans = {p["id"]: p for p in body["plans"]}
    assert list(plans) == ["free", "pro", "enterprise"]
    assert plans["free"]["price_bdt"] == 0
    assert plans["pro"] == {"id": "pro", "name": "Pro", "price_bdt": 555.0, "stories_per_month": 321}
    assert plans["enterprise"]["stories_per_month"] == settings.PLAN_LIMIT_ENTERPRISE


async def test_initiate_charges_the_settings_price(monkeypatch):
    from unittest.mock import AsyncMock
    from app.payment import sslcommerz

    monkeypatch.setattr(settings, "PLAN_PRICE_PRO_BDT", 777.0)
    monkeypatch.setattr(settings, "SSLCOMMERZ_STORE_ID", "teststore")
    monkeypatch.setattr(settings, "SSLCOMMERZ_STORE_PASS", "test-store-pass")
    gateway = AsyncMock(return_value={"status": "SUCCESS", "GatewayPageURL": "https://sandbox.example/pay"})
    monkeypatch.setattr(sslcommerz, "_create_gateway_session", gateway)
    uid = await _user()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/payment/initiate", json={"plan": "pro"}, headers=_auth(uid))
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 777.0
    assert gateway.await_args.args[0]["total_amount"] in (777.0, "777.0", "777.00")


# -- GET /payment/status/{tran_id} ---------------------------------------------

async def test_status_returns_own_payment(client):
    uid = await _user()
    tran_id = await _payment(uid, PaymentStatus.confirmed)
    r = await client.get(f"/api/v1/payment/status/{tran_id}", headers=_auth(uid))
    assert r.status_code == 200
    body = r.json()
    assert body["tran_id"] == tran_id and body["status"] == "confirmed" and body["plan"] == "pro"
    assert body["amount"] == 499.0 and body["currency"] == "BDT"


async def test_status_hides_foreign_and_unknown(client):
    owner, other = await _user(), await _user()
    tran_id = await _payment(owner)
    assert (await client.get(f"/api/v1/payment/status/{tran_id}", headers=_auth(other))).status_code == 404
    assert (await client.get("/api/v1/payment/status/SE-NOPE", headers=_auth(owner))).status_code == 404


async def test_status_requires_auth(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")  # no dev-user fallback
    owner = await _user()
    tran_id = await _payment(owner)
    assert (await client.get(f"/api/v1/payment/status/{tran_id}")).status_code == 401


# -- GET /auth/me: month-aware count -------------------------------------------

async def test_me_resets_count_from_an_earlier_month(client, monkeypatch):
    now = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(limits, "_utcnow", lambda: now)
    stale = await _user(count=7, period=datetime(2026, 10, 1, tzinfo=timezone.utc))
    current = await _user(plan=PlanTier.pro, count=4, period=datetime(2026, 11, 1, tzinfo=timezone.utc))

    body = (await client.get("/api/v1/auth/me", headers=_auth(stale))).json()
    assert body["stories_this_month"] == 0
    assert body["plan_limit"] == settings.PLAN_LIMIT_FREE

    body = (await client.get("/api/v1/auth/me", headers=_auth(current))).json()
    assert body["stories_this_month"] == 4
    assert body["plan_limit"] == settings.PLAN_LIMIT_PRO

    # Read-only: the stored counter is untouched until the next write path resets it.
    async with SessionLocal() as s:
        assert (await s.get(User, stale)).stories_this_month == 7
