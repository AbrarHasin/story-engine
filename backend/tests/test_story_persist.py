"""
Generation persistence: the full graph runs with a mocked LLM and the story row
must hold every section afterwards. Regression for run_name renaming the root
graph event, which left completed stories saved empty. Needs the live DB.
"""
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.agents.graph import get_compiled_graph
from app.agents.nodes import _bullet_list
from app.api.v1 import stories
from app.core import observability
from app.core.database import SessionLocal
from app.models.db import Story, StoryStatus, User
from app.models.schemas import StoryGenerateRequest


def _events(chunks: list[str]) -> list[tuple[str, dict]]:
    out = []
    for chunk in chunks:
        lines = chunk.strip().split("\n")
        out.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return out


def _fake_llm_factory(facts_reply: str = '["fact one", "fact two"]'):
    """One fake chat model per node; the reply depends on which node is asking."""

    def factory(role, max_tokens, temperature=0.3):
        llm = MagicMock()

        async def ainvoke(messages):
            prompt = str(messages)
            if "surprising, little-known facts" in prompt:
                content = facts_reply
            elif "JSON array" in prompt:
                content = '["bullet one", "bullet two"]'
            else:
                content = f"story text ({max_tokens})"
            resp = MagicMock()
            resp.content = content
            resp.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
            return resp

        llm.ainvoke = ainvoke
        return llm

    return factory


@pytest_asyncio.fixture
async def user():
    uid = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(User(id=uid, email=f"persist-{uid.hex[:8]}@example.com", name="persist test"))
        await db.commit()
    yield uid
    async with SessionLocal() as db:
        await db.execute(delete(Story).where(Story.user_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


@pytest_asyncio.fixture
async def stateless_graph(monkeypatch):
    """Compiled graph without the Redis checkpointer, and no Langfuse callback."""
    monkeypatch.setattr(stories, "_graph", await get_compiled_graph())
    monkeypatch.setattr(stories, "get_langfuse_callback", lambda *_a, **_k: None)


async def _generate(uid: uuid.UUID, facts_reply: str | None = None) -> tuple[uuid.UUID, list]:
    req = StoryGenerateRequest(topic="A lighthouse keeper")
    sid = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(Story(id=sid, user_id=uid, topic=req.topic, locale=req.locale, status=StoryStatus.running))
        await db.commit()
    factory = _fake_llm_factory(facts_reply) if facts_reply else _fake_llm_factory()
    with patch("app.agents.nodes._llm", side_effect=factory):
        chunks = [c async for c in stories._stream_generation(sid, req, None, None)]
    return sid, _events(chunks)


@pytest.mark.asyncio
async def test_completed_story_persists_every_section(user, stateless_graph):
    sid, events = await _generate(user)

    assert events[-1][0] == "done", events[-1]
    async with SessionLocal() as db:
        s = await db.get(Story, sid)
    assert s.status == StoryStatus.completed
    assert s.research == "bullet one\nbullet two"
    assert s.light_side == "bullet one\nbullet two"
    assert s.dark_side == "bullet one\nbullet two"
    assert s.facts == "fact one\nfact two"
    assert s.narrative and s.narrative.startswith("story text")
    assert s.final_output and s.final_output.startswith("story text")
    assert s.tokens_input > 0 and s.tokens_output > 0


@pytest.mark.asyncio
async def test_truncated_facts_reply_is_saved_as_clean_bullets(user, stateless_graph):
    sid, events = await _generate(user, facts_reply='["first fact", "second fact", "third fa')

    facts = next(d for n, d in events if n == "node_complete" and d["node"] == "facts")
    assert facts["bullets"] == ["first fact", "second fact"]
    async with SessionLocal() as db:
        s = await db.get(Story, sid)
    assert s.facts == "first fact\nsecond fact"


@pytest.mark.parametrize(
    "reply, expected",
    [
        ('["a", "b"]', ["a", "b"]),
        ('```json\n["a", "b"]\n```', ["a", "b"]),
        ('Here you go: ["a", "b"] hope it helps', ["a", "b"]),
        ('["a", "b with \\"quote\\"", "c is cut', ["a", 'b with "quote"']),
        ('```json\n["a", "b', ["a"]),
        ("- one\n- two", ["one", "two"]),
        ('"just one string"', ["just one string"]),
        ('[" ", "x"]', ["x"]),
    ],
)
def test_bullet_list(reply, expected):
    assert _bullet_list(reply) == expected


def test_langfuse_unreachable_disables_callback_and_logs_once(monkeypatch, caplog):
    monkeypatch.setattr(observability, "get_langfuse", lambda: object())
    monkeypatch.setattr(observability.settings, "LANGFUSE_HOST", "http://127.0.0.1:9")
    monkeypatch.setattr(observability, "_reach_state", {"ok": None, "checked": 0.0})
    with caplog.at_level("WARNING", logger=observability.__name__):
        assert observability.get_langfuse_callback("t") is None
        assert observability.get_langfuse_callback("t") is None
    assert sum("unreachable" in r.message for r in caplog.records) == 1


def test_langfuse_client_not_created_while_unreachable(monkeypatch):
    """Creating the client installs an OTLP exporter, so it must wait for the host."""
    monkeypatch.setattr(observability.settings, "LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setattr(observability.settings, "LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setattr(observability.settings, "LANGFUSE_HOST", "http://127.0.0.1:9")
    monkeypatch.setattr(observability, "_reach_state", {"ok": None, "checked": 0.0})
    monkeypatch.setattr(observability, "_langfuse_client", None)
    assert observability.get_langfuse() is None
    assert observability._langfuse_client is None
