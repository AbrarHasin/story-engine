"""
Story Engine — FastAPI application entry point.

Every endpoint is browsable and testable at:
  http://localhost:8000/docs   (Swagger UI)
  http://localhost:8000/redoc  (ReDoc)
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import engine, Base
from app.core.observability import get_langfuse
from app.api.v1.auth          import router as auth_router
from app.api.v1.stories      import router as stories_router
from app.api.v1.personalities import router as personalities_router
from app.payment.sslcommerz  import router as payment_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Story Engine v%s", settings.APP_VERSION)

    # Verify Langfuse connection
    lf = get_langfuse()
    if lf:
        logger.info("Langfuse connected — traces at %s", settings.LANGFUSE_HOST)
    else:
        logger.warning("Langfuse not configured — set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")

    yield  # app running

    logger.info("Shutting down")
    await engine.dispose()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Story Engine API",
    description="""
Multi-agent AI story generation platform.

## Observability
- Traces visible at **[Langfuse dashboard](http://localhost:3000)** (self-hosted OSS)
- Each story generation creates a full LangGraph trace with per-node token usage

## Quick test flow
1. `POST /api/v1/personalities` — create a personality preset
2. `POST /api/v1/stories/generate` — start generation (SSE stream)
3. `GET  /api/v1/stories/{id}` — fetch completed story
4. `POST /api/v1/payment/initiate` — upgrade plan (SSLCommerz)
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router,          prefix="/api/v1")
app.include_router(stories_router,      prefix="/api/v1")
app.include_router(personalities_router, prefix="/api/v1")
app.include_router(payment_router,       prefix="/api/v1")


# ── Health / Meta endpoints ───────────────────────────────────────────────────

@app.get("/health", tags=["Meta"], summary="Health check")
async def health():
    """Check connectivity to all dependencies."""
    import redis.asyncio as aioredis
    from sqlalchemy import text

    checks = {"status": "ok", "version": settings.APP_VERSION, "db": "ok", "redis": "ok", "langfuse": "ok"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        checks["db"] = f"error: {e}"
        checks["status"] = "degraded"

    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
    except Exception as e:
        checks["redis"] = f"error: {e}"
        checks["status"] = "degraded"

    lf = get_langfuse()
    if lf is None:
        checks["langfuse"] = "not configured"

    return JSONResponse(checks, status_code=200 if checks["status"] == "ok" else 207)


@app.get("/", tags=["Meta"], summary="API root")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "langfuse": settings.LANGFUSE_HOST,
    }
