from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.configs import settings

# ── Async (FastAPI) ──────────────────────────────────────────────────────────

async_engine = create_async_engine(
    settings.database.async_url,
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.max_overflow,
    pool_pre_ping=settings.database.pool_pre_ping,
    pool_recycle=settings.database.pool_recycle,
    pool_timeout=settings.database.pool_timeout,
    echo=settings.database.echo,
)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Sync (Celery) ────────────────────────────────────────────────────────────

sync_engine = create_engine(
    settings.database.sync_url,
    pool_size=settings.database.pool_size_sync,
    max_overflow=settings.database.max_overflow_sync,
    pool_pre_ping=settings.database.pool_pre_ping,
    pool_recycle=settings.database.pool_recycle,
    pool_timeout=settings.database.pool_timeout,
    echo=settings.database.echo,
)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


def get_sync_session() -> Session:
    return SyncSessionLocal()
