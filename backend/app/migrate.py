"""Run Alembic migrations: `python -m app.migrate [revision]` or as the `migrate` Lambda.

The deploy pipeline invokes the migrate function (Dockerfile.lambda target `migrate`)
before shifting the `live` alias. With DB_BACKEND=dataapi it reaches Aurora through the
RDS Data API, so it needs no VPC. Event: {"revision": "head"} (default) or
{"action": "current"} to report the applied revision without changing anything.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


async def _current_revision() -> str | None:
    from app.core.database import build_engine
    from sqlalchemy import pool

    eng = build_engine(poolclass=pool.NullPool)
    try:
        async with eng.connect() as conn:
            return await conn.run_sync(
                lambda c: MigrationContext.configure(c).get_current_revision()
            )
    finally:
        await eng.dispose()


def upgrade(revision: str = "head") -> None:
    command.upgrade(alembic_config(), revision)


def handler(event: dict | None, context: Any = None) -> dict:
    """Lambda entry point (target `migrate` in Dockerfile.lambda)."""
    import asyncio

    event = event or {}
    if event.get("action") == "current":
        return {"status": "ok", "revision": asyncio.run(_current_revision())}
    revision = str(event.get("revision", "head"))
    upgrade(revision)
    return {"status": "ok", "upgraded_to": revision, "revision": asyncio.run(_current_revision())}


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    upgrade(sys.argv[1] if len(sys.argv) > 1 else "head")
