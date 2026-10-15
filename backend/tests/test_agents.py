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
