"""Pieces shared by both FastAPI entry points (app.main and app.graph_main).

Nothing here imports LangGraph, an LLM SDK or the embedding model.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.client_ip import client_ip
from app.core.config import settings
from app.core.database import engine
from app.core.observability import get_langfuse, langfuse_enabled
from app.core.prod_guard import assert_production_safe

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Secrets were loaded from SSM (if configured) when settings were built; check them now.
    assert_production_safe(settings)  # refuse to start in prod with dev/missing secrets
    logger.info("Starting Story Engine v%s (RUN_ROLE=%s)", settings.APP_VERSION, settings.RUN_ROLE)

    # Langfuse is optional (local debugging); production runs with tracing off
    if get_langfuse():
        logger.info("Langfuse connected — traces at %s", settings.LANGFUSE_HOST)

    yield  # app running

    logger.info("Shutting down")
    await engine.dispose()


class ClientIPMiddleware:
    """Expose the real caller IP (API Gateway context / X-Forwarded-For) as request.state.client_ip.

    Plain ASGI (not BaseHTTPMiddleware) so SSE responses stream through untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["client_ip"] = client_ip(Request(scope))
        await self.app(scope, receive, send)


def add_common_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ClientIPMiddleware)


async def health(deep: bool = False):
    """Check connectivity to the dependencies.

    On the Data API backend the DB is only probed with `?deep=true`: a probe would wake a
    paused (0 ACU) Aurora cluster on every health check.
    """
    from sqlalchemy import text

    checks = {"status": "ok", "version": settings.APP_VERSION, "role": settings.RUN_ROLE,
              "db": "ok", "redis": "not used", "langfuse": "ok"}

    if settings.DB_BACKEND == "dataapi" and not deep:
        checks["db"] = "not checked (use ?deep=true)"
    else:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            checks["db"] = f"error: {e}"
            checks["status"] = "degraded"

    if settings.CHECKPOINTER.lower() == "redis":
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.REDIS_URL)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"
            checks["status"] = "degraded"

    if not langfuse_enabled():
        checks["langfuse"] = "disabled"
    elif get_langfuse() is None:
        checks["langfuse"] = "unavailable"

    return JSONResponse(checks, status_code=200 if checks["status"] == "ok" else 207)


def add_health(app: FastAPI) -> None:
    app.add_api_route("/health", health, methods=["GET"], tags=["Meta"], summary="Health check")
