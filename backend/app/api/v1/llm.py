"""LLM provider endpoints — inspect and smoke-test the active adapter."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.llm import get_adapter

router = APIRouter(prefix="/llm", tags=["LLM"])
# /ping runs a real inference, so it needs langchain + the provider SDK. It is mounted
# only where the LLM stack is installed (RUN_ROLE all/graph), never on story-api.
ping_router = APIRouter(prefix="/llm", tags=["LLM"])
logger = logging.getLogger(__name__)


@router.get("/config")
async def llm_config():
    """Active provider, role→model mapping, and (for local) the endpoint URL."""
    return get_adapter().info()


@ping_router.post("/ping", dependencies=[Depends(get_current_user)])
async def llm_ping():
    """Run one tiny real inference through the active adapter.

    Proves end-to-end connectivity (Claude API key valid, or the local
    Docker model is loaded and serving). Requires auth: it spends tokens
    on the Claude provider.
    """
    from langchain_core.messages import HumanMessage

    adapter = get_adapter()
    llm = adapter.chat("router", max_tokens=20, temperature=0.0)
    try:
        async with asyncio.timeout(300):
            resp = await llm.ainvoke([HumanMessage(content="Reply with the single word: pong")])
    except Exception as e:
        logger.error("LLM ping failed (%s): %s", adapter.name, e)
        raise HTTPException(status_code=503, detail=f"LLM unreachable via '{adapter.name}': {e}")

    return {
        "provider": adapter.name,
        "model": adapter.model_name("router"),
        "reply": (resp.content or "").strip(),
        "ok": True,
    }
