"""
Langfuse observability — optional, for local debugging.

Enabled only when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are both set. Production
on AWS runs with tracing off: the keys are unset and the `langfuse` package is not even
installed in the Lambda image, so everything here degrades to a no-op.

Provides:
  - Per-generation trace with all node spans
  - Token usage per node (input/output/total)
  - Latency per node
  - Full prompt/response logging
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_langfuse_client: Any = None
_checked = False


def langfuse_enabled() -> bool:
    return bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)


def get_langfuse() -> Any:
    """The Langfuse client, or None when tracing is disabled or unavailable."""
    global _langfuse_client, _checked
    if _checked:
        return _langfuse_client
    _checked = True
    if not langfuse_enabled():
        logger.info("Langfuse keys not set — tracing disabled")
        return None
    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        logger.info("Langfuse connected at %s", settings.LANGFUSE_HOST)
    except Exception as e:  # noqa: BLE001 — package missing or bad config: run untraced
        logger.warning("Langfuse unavailable (%s) — tracing disabled", e)
        _langfuse_client = None
    return _langfuse_client


def get_langfuse_callback(trace_name: str, trace_id: str | None = None) -> Any:
    """Return a LangChain/LangGraph callback handler that auto-sends traces to Langfuse.

    `trace_id` (32 hex chars) pins the Langfuse trace so the caller can link to it.
    The user and session are attached through `langfuse_metadata` in the run config.
    """
    if get_langfuse() is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        trace_context = {"trace_id": trace_id} if trace_id else None
        return CallbackHandler(trace_context=trace_context)  # type: ignore[arg-type]
    except Exception as e:
        logger.warning("Failed to create Langfuse callback for %s: %s", trace_name, e)
        return None


def flush_langfuse() -> None:
    """Send batched traces now (Lambda freezes the process after the response)."""
    if _langfuse_client is None:
        return
    try:
        _langfuse_client.flush()
    except Exception as e:  # noqa: BLE001 — tracing must never break a story
        logger.warning("Langfuse flush failed: %s", e)


def langfuse_metadata(user_id: str | None, session_id: str | None = None) -> dict:
    """Run-config metadata keys Langfuse reads to set the trace's user and session."""
    meta: dict = {}
    if user_id:
        meta["langfuse_user_id"] = user_id
    if session_id:
        meta["langfuse_session_id"] = session_id
    return meta
