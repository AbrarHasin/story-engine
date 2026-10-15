import pytest_asyncio

from app.core.database import engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine():
    """Drop pooled asyncpg connections after each test.

    Each test runs on its own event loop; a connection pooled by one loop
    cannot be reused (or closed) from the next.
    """
    yield
    await engine.dispose()