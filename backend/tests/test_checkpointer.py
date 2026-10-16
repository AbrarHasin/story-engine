"""T3: the Redis checkpointer never fails silently."""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents import graph
from app.core.config import settings


def _failing_saver():
    saver = MagicMock()
    saver.asetup = AsyncMock(side_effect=ConnectionError("redis down"))
    return saver


@pytest.fixture(autouse=True)
def _reset_status():
    graph.checkpointer_status.update(status="not_initialised", error=None)
    yield
    graph.checkpointer_status.update(status="not_initialised", error=None)


@pytest.mark.asyncio
async def test_unavailable_is_logged_and_recorded(caplog):
    with patch.object(graph.AsyncRedisSaver, "from_conn_string", return_value=_failing_saver()), \
         patch.object(settings, "CHECKPOINTER_REQUIRED", False), patch.object(settings, "APP_ENV", "development"), \
         caplog.at_level(logging.ERROR, logger="app.agents.graph"):
        assert await graph.get_redis_checkpointer() is None
    assert graph.checkpointer_status == {"status": "unavailable", "error": "ConnectionError"}
    assert "STATELESS" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("required,env", [(True, "development"), (False, "production")])
async def test_required_raises(required, env):
    with patch.object(graph.AsyncRedisSaver, "from_conn_string", return_value=_failing_saver()), \
         patch.object(settings, "CHECKPOINTER_REQUIRED", required), patch.object(settings, "APP_ENV", env):
        with pytest.raises(graph.CheckpointerUnavailable):
            await graph.get_redis_checkpointer()


@pytest.mark.asyncio
async def test_ok_is_recorded():
    saver = MagicMock(asetup=AsyncMock())
    with patch.object(graph.AsyncRedisSaver, "from_conn_string", return_value=saver):
        assert await graph.get_redis_checkpointer() is saver
    assert graph.checkpointer_status["status"] == "ok"


@pytest.mark.asyncio
async def test_generation_emits_error_when_required_checkpointer_is_down():
    import uuid
    from app.api.v1 import stories
    from app.models.schemas import StoryGenerateRequest

    with patch.object(stories, "_get_graph", AsyncMock(side_effect=graph.CheckpointerUnavailable("down"))), \
         patch.object(stories, "_mark_failed", AsyncMock()) as mark_failed:
        events = [e async for e in stories._stream_generation(
            uuid.uuid4(), StoryGenerateRequest(topic="cats"), None, MagicMock())]
    assert len(events) == 1 and events[0].startswith("event: error")
    assert "checkpointer_unavailable" in events[0]
    mark_failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_reports_unavailable_checkpointer_as_degraded():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    graph.checkpointer_status.update(status="unavailable", error="ConnectionError")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        body = (await c.get("/health")).json()
    assert body["checkpointer"] == "unavailable"
    assert body["status"] == "degraded"
