"""
LangGraph agent unit tests — run with: make test-agents
These test nodes in isolation without hitting the Anthropic API.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.state import StoryState
from app.agents.nodes import route_sections


def _base_state(**kwargs) -> StoryState:
    base = {
        "topic": "Test topic",
        "tonality": "neutral",
        "audience": "general",
        "length": "medium",
        "locale": "en",
        "include_light": True,
        "include_dark": True,
        "include_facts": True,
        "personality_prompt": None,
        "research_bullets": [],
        "light_bullets": [],
        "dark_bullets": [],
        "fact_bullets": [],
        "story_draft": None,
        "final_output": None,
        "errors": [],
        "token_usage": [],
        "run_id": None,
    }
    base.update(kwargs)
    return base  # type: ignore


def test_route_all_sections():
    state = _base_state(include_light=True, include_dark=True, include_facts=True)
    nodes = route_sections(state)
    assert "research" in nodes
    assert "light_side" in nodes
    assert "dark_side" in nodes
    assert "facts" in nodes


def test_route_minimal():
    state = _base_state(include_light=False, include_dark=False, include_facts=False)
    nodes = route_sections(state)
    assert "research" in nodes
    assert "light_side" not in nodes
    assert "dark_side" not in nodes
    assert "facts" not in nodes


@pytest.mark.asyncio
async def test_research_node_parses_json():
    from app.agents.nodes import research_node

    mock_resp = MagicMock()
    mock_resp.content = '["Fact one", "Fact two", "Fact three"]'
    mock_resp.usage_metadata = {"input_tokens": 50, "output_tokens": 30}

    with patch("app.agents.nodes._llm") as mock_llm_factory:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_resp
        mock_llm_factory.return_value = mock_llm

        result = await research_node(_base_state())

    assert len(result["research_bullets"]) == 3
    assert result["token_usage"][0]["input_tokens"] == 50


@pytest.mark.asyncio
async def test_light_side_skipped_when_disabled():
    from app.agents.nodes import light_side_node
    result = await light_side_node(_base_state(include_light=False))
    assert result["light_bullets"] == []


def test_synthesizer_cap_not_below_writer():
    from app.core.config import settings
    assert settings.MAX_TOKENS_SYNTHESIZER >= settings.MAX_TOKENS_WRITER


@pytest.mark.asyncio
async def test_synthesizer_uses_writer_sized_cap_even_if_configured_lower():
    from app.agents.nodes import synthesizer_node
    from app.core.config import settings

    mock_resp = MagicMock()
    mock_resp.content = "full story"
    mock_resp.usage_metadata = {"input_tokens": 10, "output_tokens": 10}

    with patch.object(settings, "MAX_TOKENS_SYNTHESIZER", 100), \
         patch("app.agents.nodes._llm") as factory:
        llm = AsyncMock()
        llm.ainvoke.return_value = mock_resp
        factory.return_value = llm
        await synthesizer_node(_base_state(story_draft="draft"))

    assert factory.call_args.kwargs["max_tokens"] >= settings.MAX_TOKENS_WRITER


async def _run_synth(**state_over):
    from app.agents.nodes import synthesizer_node

    mock_resp = MagicMock()
    mock_resp.content = "edited story"
    mock_resp.usage_metadata = {"input_tokens": 10, "output_tokens": 10}
    with patch("app.agents.nodes._llm") as factory:
        llm = AsyncMock()
        llm.ainvoke.return_value = mock_resp
        factory.return_value = llm
        out = await synthesizer_node(_base_state(story_draft="draft", **state_over))
    messages = llm.ainvoke.call_args.args[0]
    return out, factory, messages


@pytest.mark.asyncio
async def test_synthesizer_is_critic_editor_on_tone_and_audience():
    out, factory, messages = await _run_synth(tonality="playful", audience="teen")
    system = str(messages[0].content).lower()
    assert factory.call_args.args[0] == "synthesizer"
    assert "critical editor" in system
    for check in ("weak arguments", "unsupported facts", "tone drift", "light side", "dark side"):
        assert check in system
    assert "playful" in system and "teen" in system
    assert messages[1].content == "draft"
    assert out["final_output"] == "edited story"


@pytest.mark.asyncio
async def test_synthesizer_skips_balance_check_without_both_sides():
    _, _, messages = await _run_synth(include_dark=False)
    assert "dark side" not in str(messages[0].content).lower()


def test_synthesizer_runs_on_haiku_with_thinking_disabled(monkeypatch):
    from app.core.config import settings
    from app.llm.adapter import AnthropicAdapter

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    a = AnthropicAdapter()
    assert a.model_name("synthesizer") == "claude-haiku-5-5"
    chat = a.chat("synthesizer", max_tokens=1500, temperature=0.7)  # builds client, no API call
    assert chat.model == "claude-haiku-5-5"
    assert chat.thinking == {"type": "disabled"}


def test_graph_has_no_supervisor_node():
    from app.agents.graph import build_graph
    assert "supervisor" not in build_graph().nodes


# -- Bullet count (Spec Kit C7): at most 5 kept, short lists logged -----------

def test_counted_caps_long_lists():
    from app.agents.nodes import BULLETS_MAX, _counted
    assert _counted([f"b{i}" for i in range(8)], "light_side") == [f"b{i}" for i in range(BULLETS_MAX)]


def test_counted_keeps_and_logs_short_lists(caplog):
    from app.agents.nodes import _counted
    with caplog.at_level("WARNING", logger="app.agents.nodes"):
        assert _counted(["only one"], "dark_side") == ["only one"]
    assert "dark_side returned 1 bullets" in caplog.text


@pytest.mark.asyncio
async def test_facts_node_enforces_bullet_count():
    from app.agents import nodes

    resp = MagicMock(content='["a", "b", "c", "d", "e", "f", "g"]')
    llm = MagicMock(ainvoke=AsyncMock(return_value=resp))
    with patch.object(nodes, "_llm", return_value=llm), \
         patch.object(nodes, "_usage", return_value={}):
        out = await nodes.facts_node(_base_state())
    assert out["fact_bullets"] == ["a", "b", "c", "d", "e"]


# -- LLM resilience: timeout + bounded retry, clean error classification ------

def test_anthropic_chat_has_timeout_and_bounded_retries():
    from app.core.config import settings
    from app.llm import AnthropicAdapter

    with patch.object(settings, "LLM_TIMEOUT_SECONDS", 12.0), \
         patch.object(settings, "LLM_MAX_RETRIES", 4), \
         patch.object(settings, "ANTHROPIC_API_KEY", "sk-test"):
        model = AnthropicAdapter().chat("writer", 100, 0.5)

    assert model.default_request_timeout == 12.0  # type: ignore[attr-defined]
    assert model.max_retries == 4  # type: ignore[attr-defined]


def test_local_chat_has_timeout_and_bounded_retries():
    from app.core.config import settings
    from app.llm import LocalModelAdapter

    with patch.object(settings, "LOCAL_LLM_TIMEOUT_SECONDS", 77), \
         patch.object(settings, "LLM_MAX_RETRIES", 3):
        model = LocalModelAdapter().chat("writer", 100, 0.5)

    assert model.request_timeout == 77  # type: ignore[attr-defined]
    assert model.max_retries == 3  # type: ignore[attr-defined]


def test_resilience_defaults_are_sane():
    from app.core.config import settings
    assert settings.LLM_TIMEOUT_SECONDS > 0
    assert 0 <= settings.LLM_MAX_RETRIES <= 5


def _req():
    import httpx
    return httpx.Request("POST", "https://example.invalid/v1/messages")


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_classify_timeout(provider):
    import importlib
    from app.llm.adapter import classify_llm_error

    sdk = importlib.import_module(provider)
    code, message = classify_llm_error(sdk.APITimeoutError(request=_req()))
    assert code == "llm_timeout"
    assert "timed out" in message


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_classify_connection_error_is_unavailable(provider):
    import importlib
    from app.llm.adapter import classify_llm_error

    sdk = importlib.import_module(provider)
    code, _ = classify_llm_error(sdk.APIConnectionError(request=_req()))
    assert code == "llm_unavailable"


def test_classify_unknown_error_does_not_leak_details():
    from app.llm.adapter import classify_llm_error

    code, message = classify_llm_error(RuntimeError("secret-dsn postgres://u:p@h/db"))
    assert code == "internal_error"
    assert "secret" not in message


# -- SSE generator: own DB session, persisted research, trace ids, clean errors

import json as _json
import uuid as _uuid
from datetime import datetime, timezone
from types import SimpleNamespace


class _NoRequestSession:
    """Stands in for the request-scoped session: any use is a test failure."""

    def __getattr__(self, name):
        raise AssertionError(f"request-scoped session used: {name}")


class _FakeSessionFactory:
    def __init__(self, story):
        self.story = story
        self.opened = 0
        self.commits = 0
        self.executes = 0

    def __call__(self):
        self.opened += 1
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        return self.story

    async def execute(self, *args, **kwargs):
        self.executes += 1

    async def commit(self):
        self.commits += 1


class _FakeGraph:
    def __init__(self, events=(), exc=None):
        self.events = list(events)
        self.exc = exc
        self.config = None

    async def astream_events(self, initial, config=None, version=None):
        self.config = config
        for e in self.events:
            yield e
        if self.exc:
            raise self.exc


def _fake_story(**kw):
    base = dict(
        id=_uuid.uuid4(), user_id=_uuid.uuid4(), status=None, topic="A topic",
        tonality="neutral", audience="general", light_side=None, dark_side=None,
        facts=None, research=None, narrative=None, final_output=None,
        tokens_input=0, tokens_output=0, cost_usd=0.0, langgraph_run_id=None,
        completed_at=None, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _final_events():
    usage = [{"input_tokens": 5, "output_tokens": 7, "cost_usd": 0.001}]
    final = {
        "research_bullets": ["r1", "r2"], "light_bullets": ["l1"],
        "dark_bullets": [], "fact_bullets": [], "story_draft": "draft",
        "final_output": "final",
    }
    return [
        {"event": "on_chain_end", "name": "research",
         "data": {"output": {"research_bullets": ["r1", "r2"], "token_usage": usage}}},
        {"event": "on_chain_end", "name": "LangGraph", "data": {"output": final}},
    ]


async def _drive(monkeypatch, graph, story):
    from app.api.v1 import stories
    from app.models.schemas import StoryGenerateRequest

    factory = _FakeSessionFactory(story)
    seen: dict = {}

    def fake_callback(trace_name, trace_id=None):
        seen["trace_id"] = trace_id
        return None

    monkeypatch.setattr(stories, "_get_graph", AsyncMock(return_value=graph))
    monkeypatch.setattr(stories, "SessionLocal", factory)
    monkeypatch.setattr(stories, "get_langfuse_callback", fake_callback)

    events = []
    async for chunk in stories._stream_generation(
        story.id, StoryGenerateRequest(topic="A topic"), None, _NoRequestSession(),
    ):
        name, data = chunk.strip().split("\n", 1)
        events.append((name.removeprefix("event: "), _json.loads(data.removeprefix("data: "))))
    return events, factory, seen


@pytest.mark.asyncio
async def test_generator_persists_research_with_own_session(monkeypatch):
    story = _fake_story()
    events, factory, _ = await _drive(monkeypatch, _FakeGraph(_final_events()), story)

    assert events[-1][0] == "done"
    assert story.research == "r1\nr2"
    assert story.status.value == "completed"
    assert factory.opened >= 1 and factory.commits >= 1


@pytest.mark.asyncio
async def test_generator_completed_at_is_current_utc(monkeypatch):
    import inspect
    from app.api.v1 import stories

    story = _fake_story()
    await _drive(monkeypatch, _FakeGraph(_final_events()), story)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((story.completed_at - now).total_seconds()) < 5
    assert "datetime.utcnow" not in inspect.getsource(stories)


@pytest.mark.asyncio
async def test_generator_langfuse_user_and_trace_ids(monkeypatch):
    story = _fake_story()
    graph = _FakeGraph(_final_events())
    events, _, seen = await _drive(monkeypatch, graph, story)

    run_id = events[0][1]["run_id"]
    trace_id = run_id.replace("-", "")
    assert seen["trace_id"] == trace_id
    assert graph.config["metadata"]["langfuse_user_id"] == str(story.user_id)
    assert graph.config["metadata"]["langfuse_user_id"] != str(story.id)
    assert events[-1][1]["langfuse_trace"].endswith(f"/trace/{trace_id}")


@pytest.mark.asyncio
async def test_generator_llm_timeout_is_clean_error_event(monkeypatch):
    import anthropic
    import httpx

    err = anthropic.APITimeoutError(request=httpx.Request("POST", "https://x.invalid/secret"))
    story = _fake_story()
    events, factory, _ = await _drive(monkeypatch, _FakeGraph(exc=err), story)

    name, data = events[-1]
    assert name == "error"
    assert data["code"] == "llm_timeout"
    assert "x.invalid" not in data["message"]
    assert story.status.value == "failed"
    assert not any(n == "done" for n, _ in events)


@pytest.mark.asyncio
async def test_export_includes_research_section():
    from app.api.v1.stories import export_story

    story = _fake_story(research="r1\nr2", light_side="l1", final_output="final")
    response = await export_story(story.id, SimpleNamespace(id=story.user_id), _FakeSessionFactory(story))
    body = response.body.decode()

    assert "## Research" in body
    assert "- r1" in body and "- r2" in body
    assert body.index("## Research") < body.index("## Light Side")
