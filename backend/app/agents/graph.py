"""
Build and compile the LangGraph StateGraph.

Topology:
  START
    → [personality_injector, research, light_side, dark_side, facts]  (parallel)
    → writer
    → synthesizer
    → END

Checkpointer: Redis (langgraph-checkpoint-redis)
Observability: Langfuse callback injected per-run via config["callbacks"]
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.redis import AsyncRedisSaver

from app.agents.state import StoryState
from app.agents.nodes import (
    personality_injector_node,
    research_node,
    light_side_node,
    dark_side_node,
    facts_node,
    writer_node,
    synthesizer_node,
    route_sections,
)
from app.core.config import settings

import logging
logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    g = StateGraph(StoryState)

    # Register nodes
    g.add_node("personality_injector", personality_injector_node)
    g.add_node("research",             research_node)
    g.add_node("light_side",           light_side_node)
    g.add_node("dark_side",            dark_side_node)
    g.add_node("facts",                facts_node)
    g.add_node("writer",               writer_node)
    g.add_node("synthesizer",          synthesizer_node)

    # Entry → parallel fan-out (conditional edges); no LLM router call
    g.add_conditional_edges(
        START,
        route_sections,
        {
            "personality_injector": "personality_injector",
            "research":             "research",
            "light_side":           "light_side",
            "dark_side":            "dark_side",
            "facts":                "facts",
        },
    )

    # Fan-in: all parallel nodes → writer
    for node in ["personality_injector", "research", "light_side", "dark_side", "facts"]:
        g.add_edge(node, "writer")

    # Writer → Synthesizer → END
    g.add_edge("writer",      "synthesizer")
    g.add_edge("synthesizer", END)

    return g


async def get_compiled_graph(checkpointer=None):
    """Return compiled graph, optionally with Redis checkpointer."""
    g = build_graph()
    if checkpointer:
        return g.compile(checkpointer=checkpointer)
    return g.compile()


async def get_redis_checkpointer():
    """Create async Redis checkpointer for LangGraph state persistence."""
    try:
        saver = AsyncRedisSaver.from_conn_string(settings.REDIS_URL)
        await saver.asetup()
        return saver
    except Exception as e:
        logger.warning("Redis checkpointer unavailable (%s) — running stateless", e)
        return None
