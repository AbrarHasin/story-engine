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
        "route": None,
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


def test_graph_has_no_supervisor_node():
    from app.agents.graph import build_graph
    assert "supervisor" not in build_graph().nodes


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
