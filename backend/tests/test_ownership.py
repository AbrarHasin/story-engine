"""
Ownership tests: user B must get 404 on user A's stories and personalities,
and unauthenticated callers must not reach them at all.
Hit a live DB (no mocks), like test_api.py.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from app.core.auth import create_access_token
from app.core.database import SessionLocal
from app.main import app
from app.models.db import Personality, Story, StoryStatus, User


def _client(user: User, token: bool = True) -> AsyncClient:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {create_access_token(user.id, user.email)}"
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


@pytest_asyncio.fixture
async def world():
    """Two users; user A owns one story and one personality."""
    suffix = uuid.uuid4().hex[:8]
    a = User(id=uuid.uuid4(), email=f"owner-a-{suffix}@test.local", name="A")
    b = User(id=uuid.uuid4(), email=f"owner-b-{suffix}@test.local", name="B")
    story = Story(
        id=uuid.uuid4(), user_id=a.id, topic="A's private topic",
        status=StoryStatus.completed, final_output="A's secret story",
    )
    persona = Personality(id=uuid.uuid4(), user_id=a.id, name="A's persona", voice="pirate")
    async with SessionLocal() as db:
        db.add_all([a, b])
        await db.flush()
        db.add_all([story, persona])
        await db.commit()
    yield {"a": a, "b": b, "story_id": story.id, "persona_id": persona.id}
    async with SessionLocal() as db:
        await db.execute(delete(Story).where(Story.user_id.in_([a.id, b.id])))
        await db.execute(delete(Personality).where(Personality.user_id.in_([a.id, b.id])))
        await db.execute(delete(User).where(User.id.in_([a.id, b.id])))
        await db.commit()


# â”€â”€ Stories â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def test_owner_can_read_and_export_story(world):
    async with _client(world["a"]) as c:
        assert (await c.get(f"/api/v1/stories/{world['story_id']}")).status_code == 200
        r = await c.get(f"/api/v1/stories/{world['story_id']}/export")
        assert r.status_code == 200
        assert "A's secret story" in r.text


async def test_other_user_cannot_read_story(world):
    async with _client(world["b"]) as c:
        assert (await c.get(f"/api/v1/stories/{world['story_id']}")).status_code == 404


async def test_other_user_cannot_export_story(world):
    async with _client(world["b"]) as c:
        r = await c.get(f"/api/v1/stories/{world['story_id']}/export")
    assert r.status_code == 404
    assert "secret" not in r.text


async def test_other_user_cannot_delete_story(world):
    async with _client(world["b"]) as c:
        assert (await c.delete(f"/api/v1/stories/{world['story_id']}")).status_code == 404
    async with SessionLocal() as db:
        assert await db.get(Story, world["story_id"]) is not None


async def test_owner_can_delete_story(world):
    async with _client(world["a"]) as c:
        assert (await c.delete(f"/api/v1/stories/{world['story_id']}")).status_code == 204


# â”€â”€ Personalities â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def test_owner_can_get_update_delete_personality(world):
    pid = world["persona_id"]
    async with _client(world["a"]) as c:
        assert (await c.get(f"/api/v1/personalities/{pid}")).status_code == 200
        r = await c.put(f"/api/v1/personalities/{pid}", json={"voice": "professor"})
        assert r.status_code == 200 and r.json()["voice"] == "professor"
        assert (await c.delete(f"/api/v1/personalities/{pid}")).status_code == 204


async def test_other_user_cannot_get_personality(world):
    async with _client(world["b"]) as c:
        assert (await c.get(f"/api/v1/personalities/{world['persona_id']}")).status_code == 404


async def test_other_user_cannot_update_personality(world):
    pid = world["persona_id"]
    async with _client(world["b"]) as c:
        r = await c.put(f"/api/v1/personalities/{pid}", json={"voice": "hijacked"})
    assert r.status_code == 404
    async with SessionLocal() as db:
        assert (await db.get(Personality, pid)).voice == "pirate"


async def test_other_user_cannot_delete_personality(world):
    pid = world["persona_id"]
    async with _client(world["b"]) as c:
        assert (await c.delete(f"/api/v1/personalities/{pid}")).status_code == 404
    async with SessionLocal() as db:
        assert await db.get(Personality, pid) is not None


# â”€â”€ Authentication required â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def test_unauthenticated_requests_rejected(world, monkeypatch):
    """With a non-default secret there is no dev-user fallback: no token -> 401."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "not-the-default-secret")
    sid, pid = world["story_id"], world["persona_id"]
    async with _client(world["a"], token=False) as c:
        for method, url, kw in [
            ("GET", f"/api/v1/stories/{sid}", {}),
            ("GET", f"/api/v1/stories/{sid}/export", {}),
            ("DELETE", f"/api/v1/stories/{sid}", {}),
            ("GET", f"/api/v1/personalities/{pid}", {}),
            ("PUT", f"/api/v1/personalities/{pid}", {"json": {"voice": "x"}}),
            ("DELETE", f"/api/v1/personalities/{pid}", {}),
        ]:
            r = await c.request(method, url, **kw)
            assert r.status_code == 401, f"{method} {url} -> {r.status_code}"
