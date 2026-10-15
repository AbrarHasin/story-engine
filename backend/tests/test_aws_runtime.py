"""Runtime behaviour for Lambda behind API Gateway (spec 002 T016-T021). No AWS, no LLM."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api.v1 import stories
from app.core import observability
from app.core.client_ip import client_ip
from app.core.config import settings


# ── T017/T018: pings and the run deadline ────────────────────────────────────

async def _slow_source(items, delay):
    for item in items:
        await asyncio.sleep(delay)
        yield item


async def _collect(gen):
    return [x async for x in gen]


@pytest.mark.asyncio
async def test_paced_pings_while_a_node_is_silent():
    out = await _collect(stories._paced(_slow_source(["a", "b"], 0.25), deadline_s=5, ping_s=0.1))
    assert [x for x in out if x is not stories._PING] == ["a", "b"]
    assert out.count(stories._PING) >= 2
    assert out.index("a") > 0   # a ping went out before the first event


@pytest.mark.asyncio
async def test_paced_without_silence_sends_no_ping():
    out = await _collect(stories._paced(_slow_source(["a", "b"], 0), deadline_s=5, ping_s=1))
    assert out == ["a", "b"]


@pytest.mark.asyncio
async def test_paced_deadline_stops_and_closes_the_source():
    closed = asyncio.Event()

    async def forever():
        try:
            yield "first"
            await asyncio.sleep(3600)
            yield "never"
        finally:
            closed.set()

    out = []
    with pytest.raises(stories.RunDeadlineExceeded):
        async for x in stories._paced(forever(), deadline_s=0.3, ping_s=0.1):
            out.append(x)
    assert out[0] == "first"
    assert closed.is_set()


@pytest.mark.asyncio
async def test_paced_propagates_source_errors():
    async def boom():
        yield "a"
        raise RuntimeError("llm down")

    with pytest.raises(RuntimeError):
        await _collect(stories._paced(boom(), deadline_s=5, ping_s=1))


class _NeverEndingGraph:
    def __init__(self):
        self.config = None

    async def astream_events(self, initial, config=None, version=None):
        self.config = config
        await asyncio.sleep(3600)
        yield {}


class _Session:
    def __init__(self, story):
        self.story = story

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, model, key):
        return self.story

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_stream_marks_story_failed_at_deadline(monkeypatch):
    import uuid
    from unittest.mock import AsyncMock

    from app.models.schemas import StoryGenerateRequest

    story = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), status=None)
    monkeypatch.setattr(stories, "_get_graph", AsyncMock(return_value=_NeverEndingGraph()))
    monkeypatch.setattr(stories, "SessionLocal", lambda: _Session(story))
    monkeypatch.setattr(stories, "get_langfuse_callback", lambda trace_name, trace_id=None: None)
    monkeypatch.setattr(settings, "RUN_DEADLINE_SECONDS", 0.35)
    monkeypatch.setattr(settings, "SSE_PING_SECONDS", 0.1)

    chunks = [c async for c in stories._stream_generation(
        story.id, StoryGenerateRequest(topic="A topic"), None, None)]

    assert chunks[0].startswith("event: start")
    assert stories.SSE_PING in chunks
    assert chunks[-1].startswith("event: error")
    assert json.loads(chunks[-1].split("data: ", 1)[1])["code"] == "deadline"
    assert story.status.value == "failed"


# ── T018: Langfuse optional ──────────────────────────────────────────────────

def test_langfuse_disabled_without_keys(monkeypatch):
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "")
    monkeypatch.setattr(observability, "_checked", False)
    monkeypatch.setattr(observability, "_langfuse_client", None)
    assert observability.get_langfuse() is None
    assert observability.get_langfuse_callback("story_generation") is None
    observability.flush_langfuse()   # no-op, no error


def test_flush_calls_client_and_swallows_errors(monkeypatch):
    calls = []

    class Client:
        def flush(self):
            calls.append(1)
            raise RuntimeError("network")

    monkeypatch.setattr(observability, "_langfuse_client", Client())
    observability.flush_langfuse()
    assert calls == [1]


@pytest.mark.asyncio
async def test_health_on_dataapi_does_not_touch_db(monkeypatch):
    from app import main

    monkeypatch.setattr(settings, "DB_BACKEND", "dataapi")

    class NoEngine:
        def connect(self):
            raise AssertionError("health must not wake the DB")

    monkeypatch.setattr(main, "engine", NoEngine())
    resp = await main.health()
    body = json.loads(resp.body)
    assert body["status"] == "ok"
    assert body["db"].startswith("not checked")
    assert body["redis"] == "not used"


# ── T016: no Redis by default ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkpointer_none_by_default(monkeypatch):
    from app.agents import graph

    monkeypatch.setattr(settings, "CHECKPOINTER", "none")
    assert await graph.get_checkpointer() is None


# ── T021: client IP behind API Gateway ───────────────────────────────────────

def _request(headers: dict, peer=("127.0.0.1", 5000)) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": peer,
    })


def test_client_ip_from_api_gateway_request_context():
    ctx = json.dumps({"identity": {"sourceIp": "203.0.113.7"}, "stage": "prod"})
    req = _request({"x-amzn-request-context": ctx, "x-forwarded-for": "198.51.100.1"})
    assert client_ip(req, trust_proxy=True) == "203.0.113.7"


def test_client_ip_from_http_api_context():
    ctx = json.dumps({"http": {"sourceIp": "203.0.113.8"}})
    assert client_ip(_request({"x-amzn-request-context": ctx}), trust_proxy=True) == "203.0.113.8"


def test_client_ip_xff_takes_the_proxy_appended_entry():
    req = _request({"x-forwarded-for": "6.6.6.6, 203.0.113.9"})   # first entry is client-forged
    assert client_ip(req, trust_proxy=True) == "203.0.113.9"


def test_client_ip_ignores_headers_unless_trusted():
    req = _request({"x-forwarded-for": "203.0.113.9"}, peer=("192.0.2.1", 1234))
    assert client_ip(req, trust_proxy=False) == "192.0.2.1"


def test_client_ip_bad_context_falls_back():
    req = _request({"x-amzn-request-context": "{not json", "x-forwarded-for": "203.0.113.10"})
    assert client_ip(req, trust_proxy=True) == "203.0.113.10"


@pytest.mark.asyncio
async def test_middleware_sets_request_state(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    seen = {}

    @app.get("/_test_ip")
    async def _ip(request: Request):
        seen["ip"] = request.state.client_ip
        return {}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            ctx = json.dumps({"identity": {"sourceIp": "203.0.113.11"}})
            await c.get("/_test_ip", headers={"x-amzn-request-context": ctx})
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/_test_ip"]
    assert seen["ip"] == "203.0.113.11"


def test_cors_origins_come_from_settings():
    from app.main import app

    cors = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"][0]
    assert cors.kwargs["allow_origins"] == settings.BACKEND_CORS_ORIGINS


# ── T019: ONNX embedder selection (no model download in tests) ───────────────

def test_fastembed_backend_selected(monkeypatch):
    import sys

    from app.cache import semantic

    made = {}

    class FakeTextEmbedding:
        def __init__(self, model_name, **kw):
            made.update(model_name=model_name, **kw)

        def embed(self, texts):
            yield [0.6, 0.8]

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=FakeTextEmbedding))
    monkeypatch.setattr(settings, "EMBEDDING_BACKEND", "fastembed")
    monkeypatch.setattr(settings, "EMBEDDING_CACHE_DIR", "/opt/models")
    monkeypatch.setattr(semantic, "_model", None)
    assert semantic._embed_sync("hello") == [0.6, 0.8]
    assert made == {"model_name": settings.EMBEDDING_MODEL, "cache_dir": "/opt/models"}


# ── T015: migrate Lambda handler ─────────────────────────────────────────────

def test_migrate_handler_upgrades_to_head(monkeypatch):
    from app import migrate

    calls = []
    monkeypatch.setattr(migrate.command, "upgrade", lambda cfg, rev: calls.append(rev))

    async def current():
        return "0005"

    monkeypatch.setattr(migrate, "_current_revision", current)
    assert migrate.handler({}) == {"status": "ok", "upgraded_to": "head", "revision": "0005"}
    assert migrate.handler({"action": "current"}) == {"status": "ok", "revision": "0005"}
    assert calls == ["head"]
    assert migrate.alembic_config().get_main_option("script_location").endswith("alembic")
