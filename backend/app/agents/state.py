"""
LangGraph shared state schema.
Every node reads only the fields it needs — context-token discipline.
"""
from typing import TypedDict, Optional, Annotated
import operator


class TokenUsage(TypedDict):
    input_tokens:  int
    output_tokens: int
    cost_usd:      float


class StoryState(TypedDict):
    # ── Input (set once at entry) ────────────────────────────────────────────
    topic:          str
    tonality:       str                 # humorous | serious | inspirational | neutral
    audience:       str                 # general | children | experts | executives
    length:         str                 # short | medium | long
    locale:         str                 # en | bn | ar ...
    include_light:  bool
    include_dark:   bool
    include_facts:  bool

    # ── Personality (injected by PersonalityInjector node) ───────────────────
    personality_prompt: Optional[str]   # compiled system-prompt fragment

    # ── Sub-agent outputs (fan-out nodes write here) ─────────────────────────
    # Annotated[list, operator.add] → parallel nodes append safely
    research_bullets:   Annotated[list[str], operator.add]
    light_bullets:      Annotated[list[str], operator.add]
    dark_bullets:       Annotated[list[str], operator.add]
    fact_bullets:       Annotated[list[str], operator.add]

    # ── Writer / Synthesizer outputs ─────────────────────────────────────────
    story_draft:    Optional[str]
    final_output:   Optional[str]

    # ── Routing / control ────────────────────────────────────────────────────
    route:          Optional[str]       # set by Supervisor: "full" | "quick"
    errors:         Annotated[list[str], operator.add]

    # ── Observability ────────────────────────────────────────────────────────
    token_usage:    Annotated[list[TokenUsage], operator.add]
    run_id:         Optional[str]       # LangGraph run id → Langfuse trace id
