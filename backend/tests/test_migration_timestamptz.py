"""Migration 0005: naive timestamps -> timestamptz, round-trip without shifting instants."""
import asyncio
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

BACKEND = Path(__file__).resolve().parent.parent
TZ_COLUMNS = {
    ("users", "created_at"), ("personalities", "created_at"), ("personalities", "updated_at"),
    ("stories", "created_at"), ("stories", "completed_at"),
    ("payments", "created_at"), ("payments", "confirmed_at"), ("users", "quota_period_start"),
}
NAIVE_UTC = datetime(2026, 1, 2, 3, 4, 5)


def _alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, check=True,
                   capture_output=True)


async def _run(sql: str, params: dict | None = None):
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            # A non-UTC session zone proves the conversion does not depend on it.
            await conn.execute(text("SET TIME ZONE 'Asia/Dhaka'"))
            result = await conn.execute(text(sql), params or {})
            return result.fetchall() if result.returns_rows else None
    finally:
        await engine.dispose()


def _column_types() -> dict:
    rows = asyncio.run(_run(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND data_type LIKE 'timestamp%'"
    ))
    return {(t, c): d for t, c, d in rows}


def _created_at(user_id: str):
    return asyncio.run(_run("SELECT created_at FROM users WHERE id = :id", {"id": user_id}))[0][0]


def test_0005_round_trip_preserves_utc_instant():
    user_id = str(uuid.uuid4())
    try:
        _alembic("downgrade", "0004")
        types = _column_types()
        assert types[("users", "created_at")] == "timestamp without time zone"
        asyncio.run(_run(
            "INSERT INTO users (id, email, plan, stories_this_month, total_tokens_used, created_at) "
            "VALUES (:id, :email, 'free', 0, 0, :ts)",
            {"id": user_id, "email": f"tz-{user_id}@test.local", "ts": NAIVE_UTC},
        ))

        _alembic("upgrade", "head")
        types = _column_types()
        for col in TZ_COLUMNS:
            assert types[col] == "timestamp with time zone", col
        assert _created_at(user_id) == NAIVE_UTC.replace(tzinfo=timezone.utc)

        _alembic("downgrade", "0004")
        assert _created_at(user_id) == NAIVE_UTC
    finally:
        _alembic("upgrade", "head")
        asyncio.run(_run("DELETE FROM users WHERE id = :id", {"id": user_id}))

    assert _created_at_missing(user_id)
    assert _column_types()[("stories", "completed_at")] == "timestamp with time zone"


def _created_at_missing(user_id: str) -> bool:
    return not asyncio.run(_run("SELECT 1 FROM users WHERE id = :id", {"id": user_id}))
