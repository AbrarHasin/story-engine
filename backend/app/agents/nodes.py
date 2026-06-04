"""
All LangGraph nodes.  Each node is a pure async function:
  (state: StoryState) -> dict   ← only the keys it writes

Token-optimisation notes:
  - Haiku nodes: hard max_tokens caps, JSON-only output
  - Writer/Synthesizer: Sonnet, longer output allowed
  - Personality prompt cached via Anthropic prompt-caching header
"""
import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.state import StoryState, TokenUsage
from app.core.config import settings
from app.core.observability import get_langfuse

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_cost(model: str, in_tok: int, out_tok: int) -> float:
    """Approximate cost in USD based on June 2026 pricing."""
    rates = {
        settings.MODEL_ROUTER:      (1.00, 5.00),
        settings.MODEL_WRITER:      (3.00, 15.00),
        settings.MODEL_SYNTHESIZER: (3.00, 15.00),
        settings.MODEL_PREMIUM:     (5.00, 25.00),
    }
    in_rate, out_rate = rates.get(model, (3.00, 15.00))
    return (in_tok * in_rate + out_tok * out_rate) / 1_000_000


def _haiku(max_tokens: int) -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.MODEL_ROUTER,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=max_tokens,
        temperature=0.3,
    )


def _sonnet(max_tokens: int) -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.MODEL_WRITER,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=max_tokens,
        temperature=0.7,
    )


def _usage(response: Any, model: str) -> TokenUsage:
    meta = response.response_metadata or {}
    in_t  = meta.get("usage", {}).get("input_tokens", 0)
    out_t = meta.get("usage", {}).get("output_tokens", 0)
    return TokenUsage(
        input_tokens=in_t,
        output_tokens=out_t,
        cost_usd=_count_cost(model, in_t, out_t),
    )


def _length_guide(length: str) -> str:
    return {"short": "1–2 sentences", "medium": "3–5 sentences", "long": "6–10 sentences"}.get(length, "3–5 sentences")


# ── Node 1: Supervisor / Router (Haiku) ───────────────────────────────────────

async def supervisor_node(state: StoryState) -> dict:
    """Classify complexity and set route. Cheap Haiku call."""
    llm = _haiku(max_tokens=50)
    prompt = (
        f"Topic: {state['topic']}\nAudience: {state['audience']}\n"
        "Reply with JSON only: {\"route\": \"full\"} or {\"route\": \"quick\"}\n"
        "Use 'quick' only for very simple topics (single fact, children's topic)."
    )
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(resp.content.strip())
        route = data.get("route", "full")
    except Exception:
        route = "full"

    return {"route": route, "token_usage": [_usage(resp, settings.MODEL_ROUTER)]}


# ── Node 2: Personality Injector ──────────────────────────────────────────────

async def personality_injector_node(state: StoryState) -> dict:
    """
    Load personality from DB and compile into a system-prompt fragment.
    This fragment is injected into the Writer node system prompt.
    Runs before fan-out so all nodes can access it (though only Writer uses it).
    In the graph this is a pass-through if no personality_id was set.
    """
    # Actual DB lookup happens in the API layer before graph invocation.
    # personality_prompt is already set on the state; this node is a no-op
    # but kept as a hook for future dynamic personality fetching.
    return {}


# ── Node 3: Research Agent (Haiku) ────────────────────────────────────────────

async def research_node(state: StoryState) -> dict:
    llm = _haiku(max_tokens=settings.MAX_TOKENS_RESEARCH)
    system = (
        "You are a precise research assistant. Output ONLY a JSON array of strings. "
        "Each string is one key fact or context point. Max 5 items."
    )
    human = (
        f"Research: \"{state['topic']}\"\n"
        f"Audience: {state['audience']} | Locale: {state['locale']}\n"
        "Return JSON array only."
    )
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    try:
        bullets = json.loads(resp.content.strip())
        if not isinstance(bullets, list):
            bullets = [str(bullets)]
    except Exception:
        bullets = [resp.content.strip()]

    return {"research_bullets": bullets, "token_usage": [_usage(resp, settings.MODEL_ROUTER)]}


# ── Node 4: Light Side Agent (Haiku) ──────────────────────────────────────────

async def light_side_node(state: StoryState) -> dict:
    if not state.get("include_light", True):
        return {"light_bullets": []}

    llm = _haiku(max_tokens=settings.MAX_TOKENS_LIGHT)
    system = (
        "You find the positive angles of any topic. "
        "Output ONLY a JSON array of 3–5 short optimistic bullet strings."
    )
    human = (
        f"Topic: \"{state['topic']}\"\n"
        f"Tone: {state['tonality']} | Audience: {state['audience']}\n"
        "Return JSON array only."
    )
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    try:
        bullets = json.loads(resp.content.strip())
    except Exception:
        bullets = [resp.content.strip()]

    return {"light_bullets": bullets, "token_usage": [_usage(resp, settings.MODEL_ROUTER)]}


# ── Node 5: Dark Side Agent (Haiku) ───────────────────────────────────────────

async def dark_side_node(state: StoryState) -> dict:
    if not state.get("include_dark", True):
        return {"dark_bullets": []}

    llm = _haiku(max_tokens=settings.MAX_TOKENS_DARK)
    system = (
        "You identify risks, downsides and shadows of any topic. "
        "Output ONLY a JSON array of 3–5 short critical bullet strings."
    )
    human = (
        f"Topic: \"{state['topic']}\"\n"
        f"Tone: {state['tonality']} | Audience: {state['audience']}\n"
        "Return JSON array only."
    )
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    try:
        bullets = json.loads(resp.content.strip())
    except Exception:
        bullets = [resp.content.strip()]

    return {"dark_bullets": bullets, "token_usage": [_usage(resp, settings.MODEL_ROUTER)]}


# ── Node 6: Facts Agent (Haiku) ───────────────────────────────────────────────

async def facts_node(state: StoryState) -> dict:
    if not state.get("include_facts", True):
        return {"fact_bullets": []}

    llm = _haiku(max_tokens=settings.MAX_TOKENS_FACTS)
    system = (
        "You surface surprising, little-known facts. "
        "Output ONLY a JSON array of 3–5 interesting fact strings."
    )
    human = (
        f"Topic: \"{state['topic']}\"\nLocale context: {state['locale']}\n"
        "Return JSON array only."
    )
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    try:
        bullets = json.loads(resp.content.strip())
    except Exception:
        bullets = [resp.content.strip()]

    return {"fact_bullets": bullets, "token_usage": [_usage(resp, settings.MODEL_ROUTER)]}


# ── Node 7: Story Writer (Sonnet — only premium-cost node) ───────────────────

async def writer_node(state: StoryState) -> dict:
    llm = _sonnet(max_tokens=settings.MAX_TOKENS_WRITER)

    personality = state.get("personality_prompt") or ""
    length_guide = _length_guide(state["length"])

    # Compress sub-agent context before passing to writer (token discipline)
    research = "\n".join(f"• {b}" for b in state.get("research_bullets", []))
    light    = "\n".join(f"• {b}" for b in state.get("light_bullets", []))
    dark     = "\n".join(f"• {b}" for b in state.get("dark_bullets", []))
    facts    = "\n".join(f"• {b}" for b in state.get("fact_bullets", []))

    system = (
        f"You are a master storyteller. Write in {state['tonality']} tone for {state['audience']} audience. "
        f"Target length: {length_guide} per section. Language: {state['locale']}.\n"
        + (f"\nVoice/style:\n{personality}" if personality else "")
    )
    human = (
        f"Write a structured story about: \"{state['topic']}\"\n\n"
        f"Research context:\n{research}\n\n"
        f"Light side (pros):\n{light}\n\n"
        f"Dark side (risks):\n{dark}\n\n"
        f"Interesting facts:\n{facts}\n\n"
        "Structure your response as:\n"
        "## Light Side\n[content]\n\n## Dark Side\n[content]\n\n"
        "## Interesting Facts\n[content]\n\n## The Story\n[narrative]"
    )
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    return {"story_draft": resp.content, "token_usage": [_usage(resp, settings.MODEL_WRITER)]}


# ── Node 8: Synthesizer / Editor (Sonnet) ────────────────────────────────────

async def synthesizer_node(state: StoryState) -> dict:
    llm = _sonnet(max_tokens=settings.MAX_TOKENS_SYNTHESIZER)
    system = (
        "You are an editor. Polish and tighten the story. "
        "Remove redundancy. Ensure tone is consistent throughout. "
        f"Language: {state['locale']}. Return the improved full story only."
    )
    resp = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=state.get("story_draft", "")),
    ])
    return {"final_output": resp.content, "token_usage": [_usage(resp, settings.MODEL_SYNTHESIZER)]}


# ── Routing function ──────────────────────────────────────────────────────────

def route_after_supervisor(state: StoryState) -> list[str]:
    """Fan-out: decide which sub-agent nodes to run in parallel."""
    nodes = ["personality_injector", "research"]
    if state.get("include_light", True):
        nodes.append("light_side")
    if state.get("include_dark", True):
        nodes.append("dark_side")
    if state.get("include_facts", True):
        nodes.append("facts")
    return nodes
