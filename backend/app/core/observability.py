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


def get_langfuse() -> Langfuse:
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


def get_langfuse_callback(trace_name: str, user_id: str | None = None) -> CallbackHandler | None:
    """Return a LangChain/LangGraph callback handler that auto-sends traces to Langfuse."""
    lf = get_langfuse()
    if lf is None:
        return None
    try:
        return CallbackHandler(
            trace_name=trace_name,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning("Failed to create Langfuse callback: %s", e)
        return None
