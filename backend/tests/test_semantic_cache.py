"""
Semantic cache tests. Embeddings are faked (no model download); the DB part
hits live Postgres+pgvector like test_ownership.py.
"""
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.cache import semantic
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.db import Story, StoryStatus, User
from app.models.schemas import StoryGenerateRequest


def _vec(index: int, other: int | None = None, mix: float = 0.0) -> list[float]:
    """Unit-ish vector: 1.0 at `index`, optionally `mix` at `other`."""
    v = [0.0] * settings.EMBEDDING_DIM
    v[index] = 1.0
    if other is not None:
        v[other] = mix
    return v


def _events(chunks: list[str]) -> list[tuple[str, dict]]:
    out = []
    for c in chunks:
        ev, data = c.strip().split("\n", 1)
        out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_cache_text_covers_all_inputs_and_is_stable():
    base = semantic.cache_text("Topic", "serious", "kids", "short", "Voice: pirate")
    assert base == semantic.cache_text("Topic", "serious", "kids", "short", "Voice: pirate")
    for variant in (
        semantic.cache_text("Other", "serious", "kids", "short", "Voice: pirate"),
        semantic.cache_text("Topic", "funny", "kids", "short", "Voice: pirate"),
        semantic.cache_text("Topic", "serious", "experts", "short", "Voice: pirate"),
        semantic.cache_text("Topic", "serious", "kids", "long", "Voice: pirate"),
        semantic.cache_text("Topic", "serious", "kids", "short", None),
    ):
        assert variant != base


def test_flag_defaults_off():
    assert settings.SEMANTIC_CACHE_ENABLED is False
    assert 0.0 < settings.SEMANTIC_CACHE_THRESHOLD <= 1.0


@pytest.mark.asyncio
async def test_disabled_is_pure_passthrough(monkeypatch):
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", False)

    async def boom(_text):
        raise AssertionError("embedder must not run when the flag is off")

    monkeypatch.setattr(semantic, "embed_text", boom)

    async def inner(*_a):
        yield "event: start\ndata: {}\n\n"

    req = StoryGenerateRequest(topic="anything goes")
    out = [c async for c in semantic.with_semantic_cache(uuid.uuid4(), req, None, None, inner)]  # type: ignore[arg-type]
    assert out == ["event: start\ndata: {}\n\n"]


@pytest_asyncio.fixture
async def user_and_cleanup():
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"semcache-{suffix}@test.local", name="SC")
    async with SessionLocal() as db:
        db.add(user)
        await db.commit()
    yield user
    async with SessionLocal() as db:
        await db.execute(delete(Story).where(Story.user_id == user.id))
        await db.execute(delete(User).where(User.id == user.id))
        await db.commit()


async def _seed_completed(user: User, topic: str, vec: list[float], locale: str = "en") -> uuid.UUID:
    sid = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(Story(
            id=sid, user_id=user.id, topic=topic, locale=locale,
            status=StoryStatus.completed,
            light_side="light one\nlight two", dark_side="dark one", facts="fact one",
            narrative="the draft", final_output="the cached final story",
            tokens_input=100, tokens_output=200, cost_usd=0.19, embedding=vec,
        ))
        await db.commit()
    return sid


async def _new_running_story(user: User, req: StoryGenerateRequest) -> uuid.UUID:
    sid = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(Story(id=sid, user_id=user.id, topic=req.topic, locale=req.locale,
                     status=StoryStatus.running))
        await db.commit()
    return sid


@pytest.mark.asyncio
async def test_hit_replays_cached_story_with_zero_cost(monkeypatch, user_and_cleanup):
    user = user_and_cleanup
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_THRESHOLD", 0.9)

    async def fake_embed(_t):
        return _vec(7)

    monkeypatch.setattr(semantic, "embed_text", fake_embed)
    await _seed_completed(user, "the original topic", _vec(7, other=8, mix=0.1))

    req = StoryGenerateRequest(topic="a near duplicate topic")
    new_id = await _new_running_story(user, req)

    async def inner(*_a):
        raise AssertionError("graph must not run on a cache hit")
        yield ""  # pragma: no cover

    async with SessionLocal() as db:
        chunks = [c async for c in semantic.with_semantic_cache(new_id, req, None, db, inner)]

    events = _events(chunks)
    names = [n for n, _ in events]
    assert names[0] == "start" and names[-1] == "done"
    assert events[0][1]["cache_hit"] is True
    done = events[-1][1]
    assert done["cache_hit"] is True
    assert done["tokens"] == {"input": 0, "output": 0, "cost_usd": 0.0}
    nodes = {d["node"]: d for n, d in events if n == "node_complete"}
    assert nodes["synthesizer"]["final"] == "the cached final story"
    assert nodes["writer"]["draft"] == "the draft"
    assert nodes["light_side"]["bullets"] == ["light one", "light two"]
    assert all(d["tokens"]["cost_usd"] == 0.0 for d in nodes.values())

    async with SessionLocal() as db:
        s = await db.get(Story, new_id)
        assert s is not None
        assert s.status == StoryStatus.completed
        assert s.final_output == "the cached final story"
        assert s.cost_usd == 0.0 and s.tokens_input == 0 and s.tokens_output == 0


@pytest.mark.asyncio
async def test_below_threshold_misses_and_embedding_is_stored(monkeypatch, user_and_cleanup):
    user = user_and_cleanup
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_THRESHOLD", 0.9)

    async def fake_embed(_t):
        return _vec(20)  # orthogonal to the seeded vector -> similarity 0

    monkeypatch.setattr(semantic, "embed_text", fake_embed)
    await _seed_completed(user, "unrelated", _vec(7))

    req = StoryGenerateRequest(topic="something brand new")
    new_id = await _new_running_story(user, req)

    async def inner(story_id, *_a):
        yield 'event: start\ndata: {"story_id": "x"}\n\n'
        async with SessionLocal() as db:  # what the real generator does on completion
            s = await db.get(Story, story_id)
            assert s is not None
            s.status = StoryStatus.completed
            s.final_output = "fresh story"
            await db.commit()
        yield 'event: done\ndata: {"story_id": "x", "tokens": {"cost_usd": 0.2}}\n\n'

    async with SessionLocal() as db:
        chunks = [c async for c in semantic.with_semantic_cache(new_id, req, None, db, inner)]

    assert [n for n, _ in _events(chunks)] == ["start", "done"]
    assert "cache_hit" not in _events(chunks)[-1][1] or _events(chunks)[-1][1]["cache_hit"] is False

    async with SessionLocal() as db:
        s = await db.get(Story, new_id)
        assert s is not None and s.embedding is not None
        assert list(s.embedding)[20] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_failed_generation_stores_no_embedding(monkeypatch, user_and_cleanup):
    user = user_and_cleanup
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)

    async def fake_embed(_t):
        return _vec(30)

    monkeypatch.setattr(semantic, "embed_text", fake_embed)
    req = StoryGenerateRequest(topic="this one will fail")
    new_id = await _new_running_story(user, req)

    async def inner(*_a):
        yield 'event: start\ndata: {}\n\n'
        yield 'event: error\ndata: {"message": "boom"}\n\n'

    async with SessionLocal() as db:
        _ = [c async for c in semantic.with_semantic_cache(new_id, req, None, db, inner)]
    async with SessionLocal() as db:
        s = await db.get(Story, new_id)
        assert s is not None and s.embedding is None


@pytest.mark.asyncio
async def test_embedder_failure_falls_back_to_normal_generation(monkeypatch, user_and_cleanup):
    user = user_and_cleanup
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)

    async def broken(_t):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(semantic, "embed_text", broken)
    req = StoryGenerateRequest(topic="embedder is down")
    new_id = await _new_running_story(user, req)

    async def inner(*_a):
        yield 'event: start\ndata: {}\n\n'
        yield 'event: done\ndata: {}\n\n'

    async with SessionLocal() as db:
        chunks = [c async for c in semantic.with_semantic_cache(new_id, req, None, db, inner)]
    assert [n for n, _ in _events(chunks)] == ["start", "done"]


@pytest.mark.asyncio
async def test_locale_must_match(monkeypatch, user_and_cleanup):
    user = user_and_cleanup
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_THRESHOLD", 0.9)
    await _seed_completed(user, "bangla story", _vec(40), locale="bn")
    async with SessionLocal() as db:
        assert await semantic.find_cached(db, _vec(40), "en", 0.9) is None
        hit = await semantic.find_cached(db, _vec(40), "bn", 0.9)
        assert hit is not None and hit[1] == pytest.approx(1.0)
