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
    from app.core.observability import get_langfuse_callback, langfuse_metadata

    cb = get_langfuse_callback("story_generation", trace_id=trace_id)
    config = {"callbacks": [cb] if cb else [], "metadata": langfuse_metadata(user_id)}
    graph.astream_events(state, config=config, version="v2")  # one span per node
"""

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from app.core.config import settings
import logging
import time
import urllib.request

logger = logging.getLogger(__name__)

_langfuse_client: Langfuse | None = None

# Reachability is cached so a down Langfuse costs one short probe per interval,
# and is logged only when it changes (no per-request OTLP export errors).
_REACH_TTL_S = 60.0
_REACH_TIMEOUT_S = 1.0
_reach_state: dict = {"ok": None, "checked": 0.0}


def langfuse_reachable() -> bool:
    """True if the Langfuse host answers its health endpoint (cached for _REACH_TTL_S)."""
    now = time.monotonic()
    if _reach_state["ok"] is not None and now - _reach_state["checked"] < _REACH_TTL_S:
        return _reach_state["ok"]
    url = settings.LANGFUSE_HOST.rstrip("/") + "/api/public/health"
    try:
        with urllib.request.urlopen(url, timeout=_REACH_TIMEOUT_S) as resp:
            ok = resp.status < 500
    except Exception:
        ok = False
    if ok != _reach_state["ok"]:
        if ok:
            logger.info("Langfuse reachable at %s; tracing on", settings.LANGFUSE_HOST)
        else:
            logger.warning("Langfuse unreachable at %s; tracing off until it answers", settings.LANGFUSE_HOST)
    _reach_state.update(ok=ok, checked=now)
    return ok


def langfuse_configured() -> bool:
    return bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)


def get_langfuse() -> Langfuse | None:
    """The Langfuse client, or None if not configured or not reachable.

    The client is created only once the host answers: creating it installs an
    OpenTelemetry exporter that would log an export error for every story.
    """
    global _langfuse_client
    if _langfuse_client is None:
        if langfuse_configured():
            if not langfuse_reachable():
                return None
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
    if lf is None or not langfuse_reachable():
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
