"""
Story Engine — FastAPI application entry point.

Every endpoint is browsable and testable at:
  http://localhost:8000/docs   (Swagger UI)
  http://localhost:8000/redoc  (ReDoc)
"""
import logging

from fastapi import FastAPI

from app.core.config import settings
from app.core.observability import langfuse_enabled
from app.core.web import add_common_middleware, add_health, lifespan
from app.api.v1.auth          import router as auth_router
from app.api.v1.stories      import router as stories_router
from app.api.v1.personalities import router as personalities_router
from app.api.v1.llm           import router as llm_router
from app.payment.sslcommerz  import router as payment_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

add_common_middleware(app)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router,          prefix="/api/v1")
app.include_router(stories_router,      prefix="/api/v1")
app.include_router(personalities_router, prefix="/api/v1")
app.include_router(llm_router,           prefix="/api/v1")
app.include_router(payment_router,       prefix="/api/v1")

# ADR split-api-graph: the story-api Lambda (RUN_ROLE=api) never imports the generation
# stack. POST /api/v1/stories/generate is routed by API Gateway to story-graph
# (app.graph_main). Local dev (RUN_ROLE=all) keeps one process with everything.
if settings.RUN_ROLE.lower() != "api":
    from app.api.v1.generate import router as generate_router
    from app.api.v1.llm import ping_router

    app.include_router(generate_router, prefix="/api/v1")
    app.include_router(ping_router,     prefix="/api/v1")


# ── Health / Meta endpoints ───────────────────────────────────────────────────

add_health(app)


@app.get("/", tags=["Meta"], summary="API root")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "langfuse": settings.LANGFUSE_HOST if langfuse_enabled() else None,
    }
