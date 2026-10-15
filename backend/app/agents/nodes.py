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
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.state import StoryState, TokenUsage
from app.core.config import settings
from app.llm import get_adapter, extract_usage

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _llm(role: str, max_tokens: int, temperature: float = 0.3) -> BaseChatModel:
    """Provider-agnostic chat model — Claude API or local Docker model,
    depending on LLM_PROVIDER (see app.llm.adapter)."""
    return get_adapter().chat(role, max_tokens=max_tokens, temperature=temperature)


def _usage(response: Any, role: str) -> TokenUsage:
    adapter = get_adapter()
    return extract_usage(response, adapter.model_name(role), adapter)


def _json_loads(text: str) -> Any:
    """Tolerant JSON parse — local models often wrap JSON in ```fences``` or prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for open_ch, close_ch in (("[", "]"), ("{", "}")):
            start = text.find(open_ch)
            end = text.rfind(close_ch)
            if start != -1 and end > start:
                return json.loads(text[start:end + 1])
        raise


def _length_guide(length: str) -> str:
    return {"short": "1–2 sentences", "medium": "3–5 sentences", "long": "6–10 sentences"}.get(length, "3–5 sentences")


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
    llm = _llm("router", max_tokens=settings.MAX_TOKENS_RESEARCH)
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
        bullets = _json_loads(str(resp.content))
        if not isinstance(bullets, list):
            bullets = [str(bullets)]
    except Exception:
        bullets = [str(resp.content).strip()]

    return {"research_bullets": bullets, "token_usage": [_usage(resp, "router")]}


# ── Node 4: Light Side Agent (Haiku) ──────────────────────────────────────────

async def light_side_node(state: StoryState) -> dict:
    if not state.get("include_light", True):
        return {"light_bullets": []}

    llm = _llm("router", max_tokens=settings.MAX_TOKENS_LIGHT)
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
        bullets = _json_loads(str(resp.content))
    except Exception:
        bullets = [str(resp.content).strip()]

    return {"light_bullets": bullets, "token_usage": [_usage(resp, "router")]}


# ── Node 5: Dark Side Agent (Haiku) ───────────────────────────────────────────

async def dark_side_node(state: StoryState) -> dict:
    if not state.get("include_dark", True):
        return {"dark_bullets": []}

    llm = _llm("router", max_tokens=settings.MAX_TOKENS_DARK)
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
        bullets = _json_loads(str(resp.content))
    except Exception:
        bullets = [str(resp.content).strip()]

    return {"dark_bullets": bullets, "token_usage": [_usage(resp, "router")]}


# ── Node 6: Facts Agent (Haiku) ───────────────────────────────────────────────

async def facts_node(state: StoryState) -> dict:
    if not state.get("include_facts", True):
        return {"fact_bullets": []}

    llm = _llm("router", max_tokens=settings.MAX_TOKENS_FACTS)
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
        bullets = _json_loads(str(resp.content))
    except Exception:
        bullets = [str(resp.content).strip()]

    return {"fact_bullets": bullets, "token_usage": [_usage(resp, "router")]}


# ── Node 7: Story Writer (Sonnet — only premium-cost node) ───────────────────

async def writer_node(state: StoryState) -> dict:
    llm = _llm("writer", max_tokens=settings.MAX_TOKENS_WRITER, temperature=0.7)

    personality = state.get("personality_prompt") or ""
    length_guide = _length_guide(state["length"])
    include_light = state.get("include_light", True)
    include_dark  = state.get("include_dark", True)
    include_facts = state.get("include_facts", True)

    research = "\n".join(f"• {b}" for b in state.get("research_bullets", []))
    light    = "\n".join(f"• {b}" for b in state.get("light_bullets", []))
    dark     = "\n".join(f"• {b}" for b in state.get("dark_bullets", []))
    facts    = "\n".join(f"• {b}" for b in state.get("fact_bullets", []))

    context_parts = [f"Research context:\n{research}"]
    if include_light:
        context_parts.append(f"Light side (pros):\n{light}")
    if include_dark:
        context_parts.append(f"Dark side (risks):\n{dark}")
    if include_facts:
        context_parts.append(f"Interesting facts:\n{facts}")

    structure_parts = []
    if include_light:
        structure_parts.append("## Light Side\n[content]")
    if include_dark:
        structure_parts.append("## Dark Side\n[content]")
    if include_facts:
        structure_parts.append("## Interesting Facts\n[content]")
    structure_parts.append("## The Story\n[narrative]")

    system = (
        f"You are a master storyteller. Write in {state['tonality']} tone for {state['audience']} audience. "
        f"Target length: {length_guide} per section. Language: {state['locale']}.\n"
        + (f"\nVoice/style:\n{personality}" if personality else "")
    )
    human = (
        f"Write a structured story about: \"{state['topic']}\"\n\n"
        + "\n\n".join(context_parts)
        + "\n\nStructure your response as:\n"
        + "\n\n".join(structure_parts)
    )
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    return {"story_draft": resp.content, "token_usage": [_usage(resp, "writer")]}


# ── Node 8: Synthesizer / Editor (Sonnet) ────────────────────────────────────

async def synthesizer_node(state: StoryState) -> dict:
    # The editor returns the whole story, so it must never be capped below the writer.
    cap = max(settings.MAX_TOKENS_SYNTHESIZER, settings.MAX_TOKENS_WRITER)
    llm = _llm("synthesizer", max_tokens=cap, temperature=0.7)
    system = (
        "You are an editor. Polish and tighten the story. "
        "Remove redundancy. Ensure tone is consistent throughout. "
        f"Language: {state['locale']}. Return the improved full story only."
    )
    resp = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=state.get("story_draft", "")),
    ])
    return {"final_output": resp.content, "token_usage": [_usage(resp, "synthesizer")]}


# ── Routing function ──────────────────────────────────────────────────────────

def route_sections(state: StoryState) -> list[str]:
    """Entry fan-out: decide which sub-agent nodes to run in parallel."""
    nodes = ["personality_injector", "research"]
    if state.get("include_light", True):
        nodes.append("light_side")
    if state.get("include_dark", True):
        nodes.append("dark_side")
    if state.get("include_facts", True):
        nodes.append("facts")
    return nodes
