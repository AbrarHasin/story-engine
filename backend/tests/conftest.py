import pytest_asyncio
from sqlalchemy import text

from app.core.auth import DEV_USER_ID
from app.core.database import engine


@pytest_asyncio.fixture(autouse=True)
async def _dev_user_and_dispose_engine():
    """Seed the dev user (CI DBs are fresh), then drop pooled connections.

    Each test runs on its own event loop; a connection pooled by one loop
    cannot be reused (or closed) from the next.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, name, plan, stories_this_month, "
                "total_tokens_used, created_at) VALUES (:id, 'dev@storyengine.local', "
                "'Dev User', 'free', 0, 0, NOW()) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": str(DEV_USER_ID)},
        )
    yield
    await engine.dispose()
