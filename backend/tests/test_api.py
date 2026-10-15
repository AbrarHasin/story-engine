"""
API smoke tests — run with: make test-api
These hit a live DB (no mocks). Start infra first: make up-infra
"""
import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from app.core.auth import DEV_USER_ID, create_access_token
from app.main import app


@pytest.fixture
async def client(dev_user):
    token = create_access_token(DEV_USER_ID, "dev@storyengine.local")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "Story Engine"


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code in (200, 207)
    assert "status" in r.json()


@pytest.mark.asyncio
async def test_create_personality(client):
    r = await client.post("/api/v1/personalities/", json={
        "name": "Test Persona",
        "voice": "pirate",
        "tone": "humorous",
        "reading_level": "general",
        "banned_words": ["boring"],
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Test Persona"
    return data["id"]


@pytest.mark.asyncio
async def test_list_personalities(client):
    r = await client.get("/api/v1/personalities/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_list_stories(client):
    r = await client.get("/api/v1/stories/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Quotas and rate limits (issue #9) + generate owner check (issue #1) ──────

import uuid

from sqlalchemy import text

from app.core import limits
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models.db import Story, StoryStatus, User

GENERATE = "/api/v1/stories/generate"
BODY = {"topic": "A lighthouse keeper"}


class FakeRedis:
    """Minimal in-memory stand-in for the redis calls limits.py makes."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        return True

    async def ttl(self, key):
        return 42


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(limits, "_get_redis", lambda: fake)
    return fake


async def _set_stories_this_month(n: int):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE users SET stories_this_month = :n, plan = 'free', "
                "quota_period_start = date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' "
                "WHERE id = :id"
            ),
            {"n": n, "id": str(DEV_USER_ID)},
        )


@pytest.mark.asyncio
async def test_generate_rejects_foreign_personality(client, fake_redis):
    other_user, pid = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, plan, stories_this_month, total_tokens_used, created_at) "
                "VALUES (:u, :e, 'free', 0, 0, NOW())"
            ),
            {"u": str(other_user), "e": f"{other_user}@example.test"},
        )
        await conn.execute(
            text(
                "INSERT INTO personalities (id, user_id, name, banned_words, locale, is_default, "
                "created_at, updated_at) "
                "VALUES (:p, :u, 'theirs', '[]', 'en', false, NOW(), NOW())"
            ),
            {"p": str(pid), "u": str(other_user)},
        )
    try:
        r = await client.post(GENERATE, json={**BODY, "personality_id": str(pid)})
        assert r.status_code == 404
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM personalities WHERE id = :p"), {"p": str(pid)})
            await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(other_user)})


@pytest.mark.asyncio
async def test_generate_rejects_unknown_personality(client, fake_redis):
    r = await client.post(GENERATE, json={**BODY, "personality_id": str(uuid.uuid4())})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_generate_blocked_at_plan_limit(client, fake_redis):
    await _set_stories_this_month(settings.PLAN_LIMIT_FREE)
    try:
        r = await client.post(GENERATE, json=BODY)
        assert r.status_code == 402
    finally:
        await _set_stories_this_month(0)


@pytest.mark.asyncio
async def test_generate_rate_limited_with_retry_after(client, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)
    unknown = {**BODY, "personality_id": str(uuid.uuid4())}   # 404s fast, still counts
    assert (await client.post(GENERATE, json=unknown)).status_code == 404
    assert (await client.post(GENERATE, json=unknown)).status_code == 404
    r = await client.post(GENERATE, json=unknown)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "42"


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_redis_down(monkeypatch):
    class Broken:
        async def incr(self, key):
            raise ConnectionError("redis down")

    monkeypatch.setattr(limits, "_get_redis", lambda: Broken())
    await limits.enforce_rate_limit(DEV_USER_ID)   # must not raise


@pytest.mark.asyncio
async def test_record_completion_increments_counters(dev_user):
    await _set_stories_this_month(0)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET total_tokens_used = 0 WHERE id = :id"), {"id": str(DEV_USER_ID)}
        )
    async with SessionLocal() as db:
        await limits.record_completion(db, DEV_USER_ID, tokens=120)
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT stories_this_month, total_tokens_used FROM users WHERE id = :id"),
                {"id": str(DEV_USER_ID)},
            )
        ).one()
    assert tuple(row) == (1, 120)
    await _set_stories_this_month(0)


# ── Monthly quota reset + in-flight counting ─────────────────────────────────

FROZEN_NOW = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
MARCH_START = datetime(2026, 3, 1, tzinfo=timezone.utc)


async def _set_quota_state(stories: int, period_start: datetime | None):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE users SET stories_this_month = :n, plan = 'free', quota_period_start = :p "
                "WHERE id = :id"
            ),
            {"n": stories, "p": period_start, "id": str(DEV_USER_ID)},
        )


async def _read_quota_state():
    async with engine.begin() as conn:
        return tuple(
            (
                await conn.execute(
                    text("SELECT stories_this_month, quota_period_start FROM users WHERE id = :id"),
                    {"id": str(DEV_USER_ID)},
                )
            ).one()
        )


async def _clear_running_stories():
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM stories WHERE user_id = :id AND topic LIKE 'quota-test-%'"),
            {"id": str(DEV_USER_ID)},
        )


async def _enforce_and_start_story(tag: str) -> bool:
    """Mimic the generate handler: check quota, insert a running story, commit. True if admitted."""
    async with SessionLocal() as db:
        user = await db.get(User, DEV_USER_ID)
        try:
            await limits.enforce_quota(db, user)
        except HTTPException as e:
            assert e.status_code == 402
            await db.rollback()
            return False
        db.add(Story(user_id=DEV_USER_ID, topic=f"quota-test-{tag}", status=StoryStatus.running))
        await db.commit()
        return True


@pytest.mark.asyncio
async def test_quota_resets_when_month_changes(dev_user, monkeypatch):
    monkeypatch.setattr(limits, "_utcnow", lambda: FROZEN_NOW)
    await _set_quota_state(settings.PLAN_LIMIT_FREE, datetime(2026, 2, 1, tzinfo=timezone.utc))
    try:
        async with SessionLocal() as db:
            user = await db.get(User, DEV_USER_ID)
            await limits.enforce_quota(db, user)   # at the limit last month: must now pass
            await db.commit()
        count, period = await _read_quota_state()
        assert count == 0
        assert period == MARCH_START
    finally:
        await _set_stories_this_month(0)


@pytest.mark.asyncio
async def test_quota_not_reset_within_month(dev_user, monkeypatch):
    monkeypatch.setattr(limits, "_utcnow", lambda: FROZEN_NOW)
    await _set_quota_state(settings.PLAN_LIMIT_FREE, MARCH_START)
    try:
        async with SessionLocal() as db:
            user = await db.get(User, DEV_USER_ID)
            with pytest.raises(HTTPException) as exc:
                await limits.enforce_quota(db, user)
            assert exc.value.status_code == 402
            await db.rollback()
        count, period = await _read_quota_state()
        assert count == settings.PLAN_LIMIT_FREE
        assert period == MARCH_START
    finally:
        await _set_stories_this_month(0)


@pytest.mark.asyncio
async def test_record_completion_starts_new_period_after_month_change(dev_user, monkeypatch):
    monkeypatch.setattr(limits, "_utcnow", lambda: FROZEN_NOW)
    await _set_quota_state(7, datetime(2026, 2, 1, tzinfo=timezone.utc))
    try:
        async with SessionLocal() as db:
            await limits.record_completion(db, DEV_USER_ID, tokens=1)
        count, period = await _read_quota_state()
        assert (count, period) == (1, MARCH_START)
    finally:
        await _set_stories_this_month(0)


@pytest.mark.asyncio
async def test_in_flight_story_counts_toward_quota(dev_user, monkeypatch):
    monkeypatch.setattr(limits, "_utcnow", lambda: FROZEN_NOW)
    await _set_quota_state(settings.PLAN_LIMIT_FREE - 1, MARCH_START)
    try:
        assert await _enforce_and_start_story("a") is True    # takes the last slot
        assert await _enforce_and_start_story("b") is False   # in-flight story fills it
    finally:
        await _clear_running_stories()
        await _set_stories_this_month(0)


@pytest.mark.asyncio
async def test_concurrent_requests_cannot_overshoot_limit(dev_user, monkeypatch):
    monkeypatch.setattr(limits, "_utcnow", lambda: FROZEN_NOW)
    await _set_quota_state(settings.PLAN_LIMIT_FREE - 2, MARCH_START)
    try:
        results = await asyncio.gather(*(_enforce_and_start_story(str(i)) for i in range(6)))
        assert sum(results) == 2
    finally:
        await _clear_running_stories()
        await _set_stories_this_month(0)
