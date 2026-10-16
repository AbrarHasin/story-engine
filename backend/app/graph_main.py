"""
Story Engine — story-graph entry point (ADR split-api-graph).

Serves only POST /api/v1/stories/generate (SSE) plus /health. Runs as the story-graph
Lambda (Dockerfile.lambda target `graph`): LangGraph, the LLM SDK and the ONNX MiniLM
semantic cache live here, behind API Gateway in STREAM mode. Every other route is the
story-api Lambda (app.main with RUN_ROLE=api).

Local dev does not need this: app.main with the default RUN_ROLE=all serves everything.
"""
import logging

from fastapi import FastAPI

from app.core.config import settings
from app.core.web import add_common_middleware, add_health, lifespan
from app.api.v1.generate import router as generate_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Story Engine generation API",
    description="POST /api/v1/stories/generate — Server-Sent Events stream of node completions.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
add_common_middleware(app)
app.include_router(generate_router, prefix="/api/v1")
add_health(app)
