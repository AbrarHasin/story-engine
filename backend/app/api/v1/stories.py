"""
Story generation endpoints.

POST /api/v1/stories/generate   → SSE stream of generation events
GET  /api/v1/stories/{id}       → fetch completed story
GET  /api/v1/stories/           → list user's stories
DELETE /api/v1/stories/{id}     → delete story
"""
import asyncio
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.cache.semantic import with_semantic_cache
from app.core.database import get_db, SessionLocal
from app.core.observability import get_langfuse_callback, langfuse_metadata
from app.llm.adapter import classify_llm_error
from app.core.auth import get_current_user
from app.core.limits import enforce_quota, enforce_rate_limit, record_completion
from app.models.schemas import StoryGenerateRequest, StoryResponse
from app.models.db import Story, StoryStatus, Personality, User
from app.agents.graph import CheckpointerUnavailable, get_compiled_graph, get_redis_checkpointer
from app.agents.state import StoryState

router = APIRouter(prefix="/stories", tags=["Stories"])
logger = logging.getLogger(__name__)

# ── Shared graph instance (compiled once at startup) ─────────────────────────
_graph = None
_checkpointer = None


async def _get_graph():
    global _graph, _checkpointer
    if _graph is None:
        _checkpointer = await get_redis_checkpointer()
        _graph = await get_compiled_graph(_checkpointer)
    return _graph


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _utcnow() -> datetime:
    """Current UTC time, timezone-aware, matching the TIMESTAMP WITH TIME ZONE columns."""
    return datetime.now(timezone.utc)


async def _mark_failed(story_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        story = await session.get(Story, story_id)
        if story:
            story.status = StoryStatus.failed
            await session.commit()


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

    try:
        graph = await _get_graph()
    except CheckpointerUnavailable:
        # T3: required checkpointer is down; fail the story visibly, not stateless.
        await _mark_failed(story_id)
        yield _sse("error", {"code": "checkpointer_unavailable",
                             "message": "Story state store is unavailable; try again shortly.",
                             "story_id": str(story_id)})
        return
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
        "errors":             [],
        "token_usage":        [],
        "run_id":             run_id,
    }

    async with SessionLocal() as session:
        row = await session.get(Story, story_id)
        user_id = str(row.user_id) if row else None

    # Langfuse: real user id, and a trace id we also use to build the trace URL
    trace_id = run_id.replace("-", "")
    # Off the event loop: the first call may probe Langfuse reachability over HTTP
    cb = await asyncio.to_thread(get_langfuse_callback, "story_generation", trace_id)
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
    # Node outputs merged as they stream: the fallback if the root end event is missed
    streamed: dict = {}
    final_state: dict | None = None

    try:
        # astream_events gives us per-node events
        async for event in graph.astream_events(initial, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name", "")

            # The root run has no parents. Its name follows config["run_name"], so never match on it.
            if kind == "on_chain_end" and not event.get("parent_ids"):
                output = event.get("data", {}).get("output")
                if isinstance(output, dict):
                    final_state = output

            elif kind == "on_chain_end" and name in (
                "research", "light_side", "dark_side", "facts", "writer", "synthesizer"
            ):
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    streamed.update({k: v for k, v in output.items() if k != "token_usage"})
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

    except Exception as e:
        logger.exception("Graph execution error for story %s", story_id)
        code, message = classify_llm_error(e)

        # Mark story failed before emitting, so a client disconnect can't skip it
        await _mark_failed(story_id)

        yield _sse("error", {"code": code, "message": message, "story_id": str(story_id)})
        return

    if final_state is None:
        logger.warning("No root graph end event for story %s; persisting streamed node outputs", story_id)
        final_state = {**initial, **streamed}

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
        "langfuse_trace": f"{_get_langfuse_url()}/trace/{trace_id}",
    })


async def _get_owned_story(db: AsyncSession, story_id: uuid.UUID, user: User) -> Story | None:
    """Return the story only if it belongs to `user`; callers 404 on None (no existence leak)."""
    story = await db.get(Story, story_id)
    if story is None or story.user_id != user.id:
        return None
    return story


def _get_langfuse_url() -> str:
    from app.core.config import settings
    return (settings.LANGFUSE_PUBLIC_URL or settings.LANGFUSE_HOST).rstrip("/")


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

    **Consume in JS** (EventSource cannot POST; read the body stream with fetch,
    as `frontend/src/hooks/useGenerate.ts` does):
    ```js
    const res = await fetch('/api/v1/stories/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ topic }),
    });
    const reader = res.body.getReader();  // parse `event:` / `data:` lines
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


@router.get("/{story_id}", response_model=StoryResponse, summary="Get story by ID")
async def get_story(
    story_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story = await _get_owned_story(db, story_id, user)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.get("/", response_model=list[StoryResponse], summary="List stories")
async def list_stories(
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Story)
        .where(Story.user_id == user.id)
        .order_by(Story.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{story_id}/export", summary="Export story as Markdown")
async def export_story(
    story_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download the story as a .md file."""
    story = await _get_owned_story(db, story_id, user)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    lines = [f"# {story.topic}", ""]
    lines.append(f"> Tonality: {story.tonality} | Audience: {story.audience} | "
                 f"Generated: {story.created_at.isoformat()}")
    lines.append("")

    if story.research:
        lines.append("## Research")
        for b in story.research.split("\n"):
            if b.strip():
                lines.append(f"- {b.strip()}")
        lines.append("")

    if story.light_side:
        lines.append("## Light Side")
        for b in story.light_side.split("\n"):
            if b.strip():
                lines.append(f"- {b.strip()}")
        lines.append("")

    if story.dark_side:
        lines.append("## Dark Side")
        for b in story.dark_side.split("\n"):
            if b.strip():
                lines.append(f"- {b.strip()}")
        lines.append("")

    if story.facts:
        lines.append("## Interesting Facts")
        for b in story.facts.split("\n"):
            if b.strip():
                lines.append(f"- {b.strip()}")
        lines.append("")

    content = story.final_output or story.narrative
    if content:
        lines.append("## Story")
        lines.append(content)
        lines.append("")

    lines.append("---")
    lines.append(f"Tokens: {story.tokens_input} in / {story.tokens_output} out | "
                 f"Cost: ${story.cost_usd:.4f}")
    lines.append("Generated by Story Engine")

    md = "\n".join(lines)
    safe_name = "".join(c for c in story.topic[:50] if c.isalnum() or c in " -_").strip()

    from fastapi.responses import Response
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
    )


@router.delete("/{story_id}", status_code=204, summary="Delete story")
async def delete_story(
    story_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story = await _get_owned_story(db, story_id, user)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    await db.delete(story)
    await db.commit()
