"""Semantic cache: reuse a near-duplicate completed story instead of regenerating.

Before generation the request (topic, tonality, audience, length, personality)
is embedded locally and compared with stored story embeddings (pgvector cosine).
A hit at or above SEMANTIC_CACHE_THRESHOLD replays the stored story over the
usual SSE events with cost 0 and ``cache_hit: true``. A miss runs the normal
generator and stores the embedding once the story completes.

Disabled unless SEMANTIC_CACHE_ENABLED. Any cache failure falls back to normal
generation; the cache never blocks a story.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.db import Story, StoryStatus
from app.models.schemas import StoryGenerateRequest

logger = logging.getLogger(__name__)

_model: Any = None
_ZERO_TOKENS = {"input": 0, "output": 0, "cost_usd": 0.0}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def cache_text(
    topic: str, tonality: str, audience: str, length: str, personality_prompt: str | None
) -> str:
    """Canonical text that is embedded for a request."""
    return (
        f"topic: {topic.strip()}\n"
        f"tonality: {tonality}\n"
        f"audience: {audience}\n"
        f"length: {length}\n"
        f"personality: {personality_prompt or 'none'}"
    )


def _embed_sync(text: str) -> list[float]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    vec = _model.encode(text, normalize_embeddings=True)
    return [float(x) for x in vec]


async def embed_text(text: str) -> list[float]:
    """Embed with the local model (off the event loop; first call loads it)."""
    return await asyncio.to_thread(_embed_sync, text)


async def find_cached(
    db: AsyncSession, vec: list[float], locale: str, threshold: float
) -> tuple[Story, float] | None:
    """Nearest completed story with the same locale, if similarity >= threshold."""
    distance = Story.embedding.cosine_distance(vec)
    row = (
        await db.execute(
            select(Story, distance.label("distance"))
            .where(
                Story.embedding.is_not(None),
                Story.status == StoryStatus.completed,
                Story.final_output.is_not(None),
                Story.locale == locale,
            )
            .order_by(distance)
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    similarity = 1.0 - float(row.distance)
    return (row.Story, similarity) if similarity >= threshold else None


async def store_embedding(db: AsyncSession, story_id: uuid.UUID, vec: list[float]) -> None:
    await db.execute(update(Story).where(Story.id == story_id).values(embedding=vec))
    await db.commit()


def _bullets(text: str | None) -> list[str]:
    return [b for b in (text or "").split("\n") if b.strip()]


async def _replay(
    db: AsyncSession, story_id: uuid.UUID, src: Story, similarity: float
) -> AsyncGenerator[str, None]:
    """Copy `src` into the new story row and emit the standard SSE sequence."""
    run_id = str(uuid.uuid4())
    story = await db.get(Story, story_id)
    if story is not None:
        story.status = StoryStatus.completed
        story.light_side = src.light_side
        story.dark_side = src.dark_side
        story.facts = src.facts
        story.narrative = src.narrative
        story.final_output = src.final_output
        story.tokens_input = 0
        story.tokens_output = 0
        story.cost_usd = 0.0
        story.completed_at = datetime.utcnow()
        await db.commit()

    yield _sse("start", {
        "story_id": str(story_id), "run_id": run_id,
        "cache_hit": True, "similarity": round(similarity, 4),
    })
    for node, key, value in (
        ("light_side", "bullets", _bullets(src.light_side)),
        ("dark_side", "bullets", _bullets(src.dark_side)),
        ("facts", "bullets", _bullets(src.facts)),
        ("writer", "draft", src.narrative or ""),
        ("synthesizer", "final", src.final_output or ""),
    ):
        if value:
            yield _sse("node_complete", {"node": node, key: value, "tokens": _ZERO_TOKENS})
    yield _sse("done", {
        "story_id": str(story_id), "tokens": _ZERO_TOKENS,
        "cache_hit": True, "langfuse_trace": None,
    })


async def with_semantic_cache(
    story_id: uuid.UUID,
    request: StoryGenerateRequest,
    personality_prompt: str | None,
    db: AsyncSession,
    generate: Callable[..., AsyncGenerator[str, None]],
) -> AsyncGenerator[str, None]:
    """Wrap the story generator with a semantic cache lookup/store."""
    if not settings.SEMANTIC_CACHE_ENABLED:
        async for chunk in generate(story_id, request, personality_prompt, db):
            yield chunk
        return

    vec: list[float] | None = None
    try:
        vec = await embed_text(cache_text(
            request.topic, request.tonality, request.audience, request.length, personality_prompt,
        ))
        hit = await find_cached(db, vec, request.locale, settings.SEMANTIC_CACHE_THRESHOLD)
    except Exception:
        logger.exception("Semantic cache lookup failed; generating normally")
        hit = None

    if hit is not None:
        src, similarity = hit
        async for chunk in _replay(db, story_id, src, similarity):
            yield chunk
        return

    completed = False
    async for chunk in generate(story_id, request, personality_prompt, db):
        if chunk.startswith("event: done"):
            completed = True
        yield chunk

    if completed and vec is not None:
        try:
            await store_embedding(db, story_id, vec)
        except Exception:
            logger.exception("Could not store embedding for story %s", story_id)
