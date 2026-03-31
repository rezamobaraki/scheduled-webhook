"""SQLAlchemy engine and session factories.

Two engines are maintained:

* **async** — used by FastAPI request handlers (asyncpg).
* **sync**  — used by Celery worker tasks (psycopg 3).
"""

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings

# ── Async (FastAPI) ──────────────────────────────────────────────────────────

async_engine = create_async_engine(
    settings.db.async_url,
    pool_size=20,
    max_overflow=10,
)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency — yields one session per request."""
    async with AsyncSessionLocal() as session:
        yield session


# ── Sync (Celery) ────────────────────────────────────────────────────────────

sync_engine = create_engine(
    settings.db.sync_url,
    pool_size=10,
    max_overflow=5,
)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


def get_sync_session() -> Session:
    """Return a sync session for Celery tasks (use as a context-manager)."""
    return SyncSessionLocal()
