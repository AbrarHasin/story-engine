"""Per-user plan quota and Redis-backed rate limit for story generation (issue #9)."""
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.db import PlanTier, User

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


def enforce_quota(user: User) -> None:
    """402 when the user's plan limit is reached."""
    limit = plan_limit(user.plan)
    if limit and (user.stories_this_month or 0) >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Plan limit reached ({limit} stories/month on the {user.plan.value} plan). Upgrade to continue.",
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
    """Count one completed story and its tokens against the user (atomic UPDATE)."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            stories_this_month=User.stories_this_month + 1,
            total_tokens_used=User.total_tokens_used + tokens,
        )
    )
    await db.commit()