"""Production must never fall back to the dev user, whatever the JWT secret is."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.core import auth
from app.core.auth import (
    DEFAULT_DEV_JWT_SECRET,
    DEV_USER_ID,
    create_access_token,
    dev_user_fallback_enabled,
)
from app.core.config import settings
from app.main import app


@pytest.fixture
async def anon_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.parametrize(
    "app_env,secret,expected",
    [
        ("development", DEFAULT_DEV_JWT_SECRET, True),
        ("development", "a-real-secret-" + "x" * 32, False),
        ("production", DEFAULT_DEV_JWT_SECRET, False),
        ("PRODUCTION", DEFAULT_DEV_JWT_SECRET, False),
        ("prod", DEFAULT_DEV_JWT_SECRET, False),
    ],
)
def test_dev_user_fallback_enabled(monkeypatch, app_env, secret, expected):
    monkeypatch.setattr(settings, "APP_ENV", app_env)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", secret)
    assert dev_user_fallback_enabled() is expected


@pytest.mark.asyncio
async def test_production_without_token_is_401_even_with_default_secret(
    monkeypatch, dev_user, anon_client
):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", DEFAULT_DEV_JWT_SECRET)
    for method, path in [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/stories/"),
        ("GET", "/api/v1/personalities/"),
        ("POST", "/api/v1/stories/generate"),
    ]:
        r = await anon_client.request(method, path, json={"topic": "x"} if method == "POST" else None)
        assert r.status_code == 401, (method, path, r.status_code)


@pytest.mark.asyncio
async def test_optional_user_is_none_in_production(monkeypatch, dev_user):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", DEFAULT_DEV_JWT_SECRET)
    db = object()  # must not be touched: no token in production returns before any lookup
    assert await auth.get_optional_user(token=None, db=db) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_production_accepts_a_valid_bearer_token(monkeypatch, dev_user, anon_client):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    token = create_access_token(DEV_USER_ID, "dev@storyengine.local")
    r = await anon_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["id"] == str(DEV_USER_ID)


@pytest.mark.asyncio
async def test_development_default_secret_still_falls_back(monkeypatch, dev_user, anon_client):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", DEFAULT_DEV_JWT_SECRET)
    r = await anon_client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["id"] == str(DEV_USER_ID)
