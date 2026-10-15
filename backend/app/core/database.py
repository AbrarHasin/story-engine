from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects import registry
from sqlalchemy.orm import DeclarativeBase
from app.core.config import Settings, settings

registry.register("postgresql.dataapi", "app.core.dataapi", "PGDialect_dataapi")


def build_engine(s: Settings = settings, **overrides: Any) -> AsyncEngine:
    """Async engine for DB_BACKEND: asyncpg (local) or the RDS Data API (AWS)."""
    if s.DB_BACKEND == "dataapi":
        return create_async_engine(
            "postgresql+dataapi://",
            echo=s.DEBUG,
            connect_args={
                "resource_arn": s.DATAAPI_RESOURCE_ARN,
                "secret_arn": s.DATAAPI_SECRET_ARN,
                "database": s.DATAAPI_DATABASE,
                "resume_timeout": s.DATAAPI_RESUME_TIMEOUT_SECONDS,
            },
            **overrides,
        )
    if s.DB_BACKEND != "asyncpg":
        raise ValueError(f"Unknown DB_BACKEND {s.DB_BACKEND!r} (expected asyncpg or dataapi)")
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if "poolclass" not in overrides:
        kwargs.update(pool_size=10, max_overflow=20)
    return create_async_engine(s.DATABASE_URL, echo=s.DEBUG, **kwargs, **overrides)


engine = build_engine()

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
