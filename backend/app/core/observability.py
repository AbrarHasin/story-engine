"""
Langfuse observability — free OSS alternative to LangSmith.
Self-hosted at http://localhost:3000

Provides:
  - Per-generation trace with all node spans
  - Token usage per node (input/output/total)
  - Latency per node
  - Cost estimates
  - Full prompt/response logging

Usage:
    from app.core.observability import get_tracer, trace_node

    tracer = get_tracer()
    with tracer.trace("story_generation", user_id="u123") as trace:
        with trace.span("supervisor_node") as span:
            span.update(input={"topic": "AI"}, output={"route": "full"})
"""

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

_langfuse_client: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    global _langfuse_client
    if _langfuse_client is None:
        if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
            _langfuse_client = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_HOST,
            )
            logger.info("Langfuse connected at %s", settings.LANGFUSE_HOST)
        else:
            logger.warning(
                "LANGFUSE_PUBLIC_KEY/SECRET_KEY not set — traces will be NO-OP. "
                "Set keys via docker-compose or .env to enable trace UI at %s",
                settings.LANGFUSE_HOST,
            )
            _langfuse_client = None
    return _langfuse_client


def get_langfuse_callback(trace_name: str, trace_id: str | None = None) -> CallbackHandler | None:
    """Return a LangChain/LangGraph callback handler that auto-sends traces to Langfuse.

    `trace_id` (32 hex chars) pins the Langfuse trace so the caller can link to it.
    The user and session are attached through `langfuse_metadata` in the run config.
    """
    lf = get_langfuse()
    if lf is None:
        return None
    try:
        trace_context = {"trace_id": trace_id} if trace_id else None
        return CallbackHandler(trace_context=trace_context)  # type: ignore[arg-type]
    except Exception as e:
        logger.warning("Failed to create Langfuse callback for %s: %s", trace_name, e)
        return None


def langfuse_metadata(user_id: str | None, session_id: str | None = None) -> dict:
    """Run-config metadata keys Langfuse reads to set the trace's user and session."""
    meta: dict = {}
    if user_id:
        meta["langfuse_user_id"] = user_id
    if session_id:
        meta["langfuse_session_id"] = session_id
    return meta
