"""Run Alembic migrations: `python -m app.migrate [revision]` or as the `migrate` Lambda.

The deploy pipeline invokes the migrate function (Dockerfile.lambda target `migrate`)
before shifting the `live` alias. With DB_BACKEND=dataapi it reaches Aurora through the
RDS Data API, so it needs no VPC. Event: {"revision": "head"} (default) or
{"action": "current"} to report the applied revision without changing anything.

As the CodeDeploy PreTraffic hook the event carries DeploymentId and
LifecycleEventHookExecutionId: the handler migrates to head, then reports Succeeded or
Failed with codedeploy:PutLifecycleEventHookExecutionStatus (Failed on any exception,
after logging it), so traffic only moves to the new version after a good migration.
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


def _codedeploy_client() -> Any:
    import boto3

    return boto3.client("codedeploy")


def _hook_ids(event: dict) -> tuple[str, str] | None:
    dep, hook = event.get("DeploymentId"), event.get("LifecycleEventHookExecutionId")
    return (str(dep), str(hook)) if dep and hook else None


def _migrate(event: dict) -> dict:
    import asyncio

    if event.get("action") == "current":
        return {"status": "ok", "revision": asyncio.run(_current_revision())}
    revision = str(event.get("revision", "head"))
    upgrade(revision)
    return {"status": "ok", "upgraded_to": revision, "revision": asyncio.run(_current_revision())}


def handler(event: dict | None, context: Any = None) -> dict:
    """Lambda entry point (target `migrate` in Dockerfile.lambda)."""
    event = event or {}
    ids = _hook_ids(event)
    if ids is None:
        return _migrate(event)  # manual invoke: errors propagate to the caller

    deployment_id, hook_id = ids
    try:
        result = _migrate({"revision": "head"})
        status = "Succeeded"
    except Exception as exc:
        logger.exception("Migration failed during CodeDeploy hook %s", deployment_id)
        result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        status = "Failed"

    _codedeploy_client().put_lifecycle_event_hook_execution_status(
        deploymentId=deployment_id,
        lifecycleEventHookExecutionId=hook_id,
        status=status,
    )
    logger.info("Reported %s to CodeDeploy deployment %s", status, deployment_id)
    return {**result, "hook_status": status}


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    upgrade(sys.argv[1] if len(sys.argv) > 1 else "head")
