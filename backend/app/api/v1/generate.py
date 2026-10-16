"""
Story generation: POST /api/v1/stories/generate (SSE stream).

Runs LangGraph and the semantic cache. On AWS this module is mounted only by the
story-graph Lambda (app.graph_main, image target `graph`); the story-api Lambda
(RUN_ROLE=api, image target `api`) never imports it, so LangGraph, the LLM SDKs
and the ONNX model stay out of its image and cold start. JWT auth, personality
ownership, rate limit and quota run here too (shared app.core code).
"""
import asyncio
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.semantic import with_semantic_cache
from app.core.database import get_db, SessionLocal
from app.core.config import settings
from app.core.observability import flush_langfuse, get_langfuse_callback, langfuse_metadata
from app.llm.adapter import classify_llm_error
from app.core.auth import get_current_user
from app.core.limits import enforce_quota, enforce_rate_limit, record_completion
from app.models.schemas import StoryGenerateRequest
from app.models.db import Story, StoryStatus, Personality, User
from app.agents.graph import get_checkpointer, get_compiled_graph
from app.agents.state import StoryState

router = APIRouter(prefix="/stories", tags=["Stories"])
logger = logging.getLogger(__name__)

# ── Shared graph instance (compiled once at startup) ─────────────────────────
_graph = None
_checkpointer = None


async def _get_graph():
    global _graph, _checkpointer
    if _graph is None:
        _checkpointer = await get_checkpointer()
        _graph = await get_compiled_graph(_checkpointer)
    return _graph


# ── SSE helpers ───────────────────────────────────────────────────────────────

SSE_PING = ": ping\n\n"   # SSE comment: clients ignore it, idle timeouts see traffic


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class RunDeadlineExceeded(Exception):
    """The graph ran past RUN_DEADLINE_SECONDS."""


_PING = object()


async def _paced(
    source: AsyncIterator[Any], deadline_s: float, ping_s: float
) -> AsyncGenerator[Any, None]:
    """Yield items from `source`, `_PING` after every `ping_s` of silence, and raise
    RunDeadlineExceeded once `deadline_s` has passed (the source is closed first)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + deadline_s
    it = source.__aiter__()
    pending: asyncio.Future | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise RunDeadlineExceeded()
            wait = min(remaining, ping_s) if ping_s > 0 else remaining
            done, _ = await asyncio.wait({pending}, timeout=wait)
            if not done:
                if loop.time() >= deadline:
                    raise RunDeadlineExceeded()
                yield _PING
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                pending = None
                return
            pending = None
            yield item
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration, Exception):  # noqa: BLE001
                pass
        aclose = getattr(it, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:  # noqa: BLE001 — best effort
                logger.debug("closing the graph stream failed", exc_info=True)


def _utcnow() -> datetime:
    """Current UTC time as naive UTC, matching the TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _stream_generation(
    story_id: uuid.UUID,
    request: StoryGenerateRequest,
    personality_prompt: str | None,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Run LangGraph and stream SSE events for each node completion.

    The request-scoped `db` is closed once the handler returns, so the generator
    never touches it: it opens its own short-lived sessions instead.
    """

    graph = await _get_graph()
    run_id = str(uuid.uuid4())

    # Build initial state
    initial: StoryState = {
        "topic":              request.topic,
        "tonality":           request.tonality,
        "audience":           request.audience,
        "length":             request.length,
        "locale":             request.locale,
        "include_light":      request.include_light,
        "include_dark":       request.include_dark,
        "include_facts":      request.include_facts,
        "personality_prompt": personality_prompt,
        "research_bullets":   [],
        "light_bullets":      [],
        "dark_bullets":       [],
        "fact_bullets":       [],
        "story_draft":        None,
        "final_output":       None,
        "route":              None,
        "errors":             [],
        "token_usage":        [],
        "run_id":             run_id,
    }

    async with SessionLocal() as session:
        row = await session.get(Story, story_id)
        user_id = str(row.user_id) if row else None

    # Langfuse: real user id, and a trace id we also use to build the trace URL
    trace_id = run_id.replace("-", "")
    cb = get_langfuse_callback(trace_name="story_generation", trace_id=trace_id)
    config = {
        "configurable": {"thread_id": str(story_id)},
        "callbacks": [cb] if cb else [],
        "metadata": langfuse_metadata(user_id, str(story_id)),
        "run_name": "story_generation",
        "run_id": run_id,
    }

    yield _sse("start", {"story_id": str(story_id), "run_id": run_id})

    total_input = 0
    total_output = 0
    total_cost = 0.0
    final_state = initial

    try:
        # astream_events gives us per-node events; _paced adds pings and the run deadline
        events = graph.astream_events(initial, config=config, version="v2")
        async for event in _paced(events, settings.RUN_DEADLINE_SECONDS, settings.SSE_PING_SECONDS):
            if event is _PING:
                yield SSE_PING
                continue
            kind = event.get("event")
            name = event.get("name", "")

            if kind == "on_chain_end" and name in (
                "research", "light_side", "dark_side", "facts", "writer", "synthesizer"
            ):
                output = event.get("data", {}).get("output", {})
                # Emit node completion to client
                payload: dict = {"node": name}

                if name == "research":
                    payload["bullets"] = output.get("research_bullets", [])
                elif name == "light_side":
                    payload["bullets"] = output.get("light_bullets", [])
                elif name == "dark_side":
                    payload["bullets"] = output.get("dark_bullets", [])
                elif name == "facts":
                    payload["bullets"] = output.get("fact_bullets", [])
                elif name == "writer":
                    payload["draft"] = output.get("story_draft", "")
                elif name == "synthesizer":
                    payload["final"] = output.get("final_output", "")

                # Aggregate token usage
                for usage in output.get("token_usage", []):
                    total_input  += usage["input_tokens"]
                    total_output += usage["output_tokens"]
                    total_cost   += usage["cost_usd"]

                payload["tokens"] = {"input": total_input, "output": total_output, "cost_usd": round(total_cost, 6)}
                yield _sse("node_complete", payload)

            elif kind == "on_chain_end" and name == "LangGraph":
                final_state = event.get("data", {}).get("output", {})

    except Exception as e:
        if isinstance(e, RunDeadlineExceeded):
            logger.error("Story %s passed the %.0f s run deadline", story_id, settings.RUN_DEADLINE_SECONDS)
            code, message = "deadline", "The story took too long and was stopped. Please try again."
        else:
            logger.exception("Graph execution error for story %s", story_id)
            code, message = classify_llm_error(e)

        # Mark story failed before emitting, so a client disconnect can't skip it
        async with SessionLocal() as session:
            story = await session.get(Story, story_id)
            if story:
                story.status = StoryStatus.failed
                await session.commit()

        yield _sse("error", {"code": code, "message": message, "story_id": str(story_id)})
        return
    finally:
        # Lambda freezes after the response: send batched traces now (no-op when disabled)
        flush_langfuse()

    # Authoritative totals: sum every node's usage from the final state
    final_usage = final_state.get("token_usage") or []
    if final_usage:
        total_input  = sum(u["input_tokens"] for u in final_usage)
        total_output = sum(u["output_tokens"] for u in final_usage)
        total_cost   = sum(u["cost_usd"] for u in final_usage)

    # Persist completed story
    async with SessionLocal() as session:
        story = await session.get(Story, story_id)
        if story:
            story.status        = StoryStatus.completed
            story.research      = "\n".join(final_state.get("research_bullets", []))
            story.light_side    = "\n".join(final_state.get("light_bullets", []))
            story.dark_side     = "\n".join(final_state.get("dark_bullets", []))
            story.facts         = "\n".join(final_state.get("fact_bullets", []))
            story.narrative     = final_state.get("story_draft")
            story.final_output  = final_state.get("final_output")
            story.tokens_input  = total_input
            story.tokens_output = total_output
            story.cost_usd      = total_cost
            story.langgraph_run_id = run_id
            story.completed_at  = _utcnow()
            await session.commit()
            await record_completion(session, story.user_id, total_input + total_output)

    yield _sse("done", {
        "story_id": str(story_id),
        "tokens": {"input": total_input, "output": total_output, "cost_usd": round(total_cost, 6)},
        "langfuse_trace": f"{_get_langfuse_url()}/trace/{trace_id}" if cb else None,
    })


def _get_langfuse_url() -> str:
    return settings.LANGFUSE_HOST


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/generate",
    summary="Generate a story (SSE stream)",
    response_description="Server-Sent Events stream of node completions",
)
async def generate_story(
    request: StoryGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Stream story generation via Server-Sent Events.

    **Events emitted:**
    - `start` — generation started, includes story_id
    - `node_complete` — each agent node finished (research, light_side, dark_side, facts, writer, synthesizer)
    - `done` — generation complete, includes token usage and Langfuse trace URL
    - `error` — unrecoverable error

    **Consume in JS:**
    ```js
    const es = new EventSource('/api/v1/stories/generate', { method: 'POST' });
    es.addEventListener('node_complete', e => console.log(JSON.parse(e.data)));
    ```
    """
    await enforce_rate_limit(user.id)
    await enforce_quota(db, user)

    # Resolve personality (owner-scoped: 404 for unknown or foreign ids, no existence leak)
    personality_prompt: str | None = None
    if request.personality_id:
        p = await db.get(Personality, request.personality_id)
        if p is None or p.user_id != user.id:
            raise HTTPException(status_code=404, detail="Personality not found")
        if p:
            parts = []
            if p.voice:
                parts.append(f"Voice: {p.voice}")
            if p.tone:
                parts.append(f"Tone: {p.tone}")
            if p.reading_level:
                parts.append(f"Reading level: {p.reading_level}")
            if p.banned_words:
                parts.append(f"Never use these words: {', '.join(p.banned_words)}")
            personality_prompt = "\n".join(parts)

    # Create pending story record
    story = Story(
        id=uuid.uuid4(),
        user_id=user.id,
        personality_id=request.personality_id,
        topic=request.topic,
        tonality=request.tonality,
        audience=request.audience,
        length=request.length,
        locale=request.locale,
        status=StoryStatus.running,
    )
    db.add(story)
    await db.commit()

    return StreamingResponse(
        with_semantic_cache(story.id, request, personality_prompt, db, _stream_generation),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Nginx: disable proxy buffering for SSE
        },
    )
