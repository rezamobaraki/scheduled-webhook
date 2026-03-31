"""Integration test fixtures — requires PostgreSQL and Redis via Docker.

    docker compose up postgres redis -d
    uv run pytest tests/integration -v
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.configs import settings
from src.core.database import SyncSessionLocal, get_async_session
from src.main import app

# ── Test-specific async engine (avoids event-loop mismatch) ──────────────────

_test_async_engine = create_async_engine(settings.database.async_url, pool_size=5)
_TestAsyncSessionLocal = async_sessionmaker(_test_async_engine, expire_on_commit=False)
_ALEMBIC_CONFIG = Config(str(Path(__file__).parents[2] / "alembic.ini"))


# ── Database lifecycle ───────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Reset the schema and build it through Alembic migrations."""
    engine = create_engine(settings.database.sync_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(_ALEMBIC_CONFIG, "head")
    yield
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
async def _dispose_async_engine():
    """Dispose the test async engine after all tests complete."""
    yield
    await _test_async_engine.dispose()


@pytest.fixture(autouse=True)
def _clean_db():
    """Truncate every table after each test for perfect isolation."""
    yield
    with SyncSessionLocal() as session:
        session.execute(text("DELETE FROM timers"))
        session.commit()


# ── Session fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture(loop_scope="session")
async def async_session() -> AsyncGenerator[AsyncSession]:
    """Async session for use in API tests (injected into FastAPI)."""
    async with _TestAsyncSessionLocal() as session:
        yield session


@pytest.fixture
def sync_session():
    """Sync session for use in Celery task tests."""
    with SyncSessionLocal() as session:
        yield session


# ── Celery mock ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_fire_webhook(monkeypatch):
    """Replace ``fire_webhook.apply_async`` with a no-op mock.

    Prevents real Celery messages from being dispatched during API tests.
    """
    mock = MagicMock()
    monkeypatch.setattr("src.worker.tasks.fire_webhook.apply_async", mock)
    return mock


# ── HTTP client ──────────────────────────────────────────────────────────────


@pytest.fixture
async def client(
    async_session: AsyncSession,
    mock_fire_webhook,
) -> AsyncGenerator[AsyncClient]:
    """``httpx.AsyncClient`` wired to the FastAPI app with overridden deps."""

    async def _override():
        yield async_session

    app.dependency_overrides[get_async_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
