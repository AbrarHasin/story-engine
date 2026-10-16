"""Per-user plan quota and Postgres-backed rate limit for story generation (issue #9).

The rate limit lives in the `rate_limit_window` table (migration 0005), so the app needs
no Redis: one auto-committed upsert per generate call, one Data API request on AWS.
"""
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import engine
from app.models.db import PlanTier, RateLimitWindow, Story, StoryStatus, User

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW_SECONDS = 60


def plan_limit(plan: PlanTier) -> int:
    """Completed stories allowed per month for `plan`; 0 means unlimited."""
    return {
        PlanTier.free: settings.PLAN_LIMIT_FREE,
        PlanTier.pro: settings.PLAN_LIMIT_PRO,
        PlanTier.enterprise: settings.PLAN_LIMIT_ENTERPRISE,
    }[plan]


def _utcnow() -> datetime:
    """Current UTC time; a seam so tests can freeze the clock."""
    return datetime.now(timezone.utc)


def _period_start(now: datetime) -> datetime:
    """First instant of the calendar month (UTC) containing `now`."""
    return now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _stale_running_cutoff(now: datetime) -> datetime:
    """`running` stories created before this are dead runs (Lambda timeout skipped `finally`).

    Naive UTC, matching stories.created_at (TIMESTAMP WITHOUT TIME ZONE).
    """
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=settings.STALE_RUNNING_MINUTES)
    return cutoff.replace(tzinfo=None)


async def enforce_quota(db: AsyncSession, user: User) -> None:
    """402 when completed + in-flight stories reach the user's plan limit.

    Locks the user row (SELECT ... FOR UPDATE) and lazily resets the monthly counter when the
    calendar month (UTC) differs from `quota_period_start`. Nothing is committed here: the lock
    and the reset live in the caller's transaction until it commits (right after it inserts the
    running Story), so concurrent requests serialise and cannot overshoot the limit.
    In-flight = `running` stories younger than STALE_RUNNING_MINUTES.
    """
    row = (
        await db.execute(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    now = _utcnow()
    period = _period_start(now)
    if row.quota_period_start is None or row.quota_period_start < period:
        row.stories_this_month = 0
        row.quota_period_start = period

    limit = plan_limit(row.plan)
    if not limit:
        return
    in_flight = (
        await db.execute(
            select(func.count())
            .select_from(Story)
            .where(
                Story.user_id == row.id,
                Story.status == StoryStatus.running,
                Story.created_at >= _stale_running_cutoff(now),
            )
        )
    ).scalar_one()
    if (row.stories_this_month or 0) + in_flight >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Plan limit reached ({limit} stories/month on the {row.plan.value} plan). Upgrade to continue.",
        )


async def _hit_rate_window(key: str, now: datetime) -> tuple[int, datetime]:
    """Count one call in `key`'s fixed window; start a new window once the old one is over.

    A single upsert, auto-committed on its own connection: a 402/404 later in the request
    rolls back the request transaction but must not undo the count.
    """
    expired = RateLimitWindow.window_start <= now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    stmt = insert(RateLimitWindow).values(key=key, window_start=now, count=1).on_conflict_do_update(
        index_elements=[RateLimitWindow.key],
        set_={
            "count": case((expired, 1), else_=RateLimitWindow.count + 1),
            "window_start": case((expired, now), else_=RateLimitWindow.window_start),
        },
    ).returning(RateLimitWindow.count, RateLimitWindow.window_start)
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        row = (await conn.execute(stmt)).one()
    return int(row[0]), row[1]


async def enforce_rate_limit(user_id: uuid.UUID) -> None:
    """429 + Retry-After when the user exceeds RATE_LIMIT_PER_MINUTE (fixed 60s window).

    Fails open if the database call fails: the limiter must not block generation on its own.
    """
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return
    now = _utcnow()
    try:
        count, window_start = await _hit_rate_window(f"generate:{user_id}", now)
    except Exception as e:  # noqa: BLE001 — limiter failure fails open
        logger.warning("Rate limiter unavailable (%s) — allowing request", e)
        return
    if count <= limit:
        return
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    remaining = (window_start + timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS) - now).total_seconds()
    raise HTTPException(
        status_code=429,
        detail="Too many generate requests. Slow down.",
        headers={"Retry-After": str(max(math.ceil(remaining), 1))},
    )


async def record_completion(db: AsyncSession, user_id: uuid.UUID, tokens: int) -> None:
    """Count one completed story and its tokens against the user (atomic UPDATE).

    A story that finishes in a later month than the stored period starts the new period at 1.
    """
    period = _period_start(_utcnow())
    stale = User.quota_period_start.is_(None) | (User.quota_period_start < period)
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            stories_this_month=case((stale, 1), else_=User.stories_this_month + 1),
            quota_period_start=case((stale, period), else_=User.quota_period_start),
            total_tokens_used=User.total_tokens_used + tokens,
        )
    )
    await db.commit()
