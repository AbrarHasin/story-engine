"""
API smoke tests — run with: make test-api
These hit a live DB (no mocks). Start infra first: make up-infra
"""
import pytest
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
