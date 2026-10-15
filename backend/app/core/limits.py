"""Per-user plan quota and Redis-backed rate limit for story generation (issue #9)."""
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.db import PlanTier, Story, StoryStatus, User

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL)
    return _redis


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


async def enforce_quota(db: AsyncSession, user: User) -> None:
    """402 when completed + in-flight stories reach the user's plan limit.

    Locks the user row (SELECT ... FOR UPDATE) and lazily resets the monthly counter when the
    calendar month (UTC) differs from `quota_period_start`. Nothing is committed here: the lock
    and the reset live in the caller's transaction until it commits (right after it inserts the
    running Story), so concurrent requests serialise and cannot overshoot the limit.
    """
    row = (
        await db.execute(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    period = _period_start(_utcnow())
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
            .where(Story.user_id == row.id, Story.status == StoryStatus.running)
        )
    ).scalar_one()
    if (row.stories_this_month or 0) + in_flight >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Plan limit reached ({limit} stories/month on the {row.plan.value} plan). Upgrade to continue.",
        )


async def enforce_rate_limit(user_id: uuid.UUID) -> None:
    """429 + Retry-After when the user exceeds RATE_LIMIT_PER_MINUTE (fixed 60s window).

    Fails open if Redis is unreachable: a cache outage must not block generation.
    """
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return
    key = f"ratelimit:generate:{user_id}"
    try:
        r = _get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 60)
        if count <= limit:
            return
        retry_after = await r.ttl(key)
    except Exception as e:  # noqa: BLE001 — any Redis failure fails open
        logger.warning("Rate limiter unavailable (%s) — allowing request", e)
        return
    raise HTTPException(
        status_code=429,
        detail="Too many generate requests. Slow down.",
        headers={"Retry-After": str(max(int(retry_after), 1))},
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