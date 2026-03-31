"""Shared test fixtures.

Requirements to run the test suite::

    docker compose up postgres redis -d
    uv sync --dev
    uv run pytest -v
"""

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.core.database import SyncSessionLocal, get_async_session
from src.main import app
from src.models import BaseModel

# ── Test-specific async engine (avoids event-loop mismatch) ──────────────────

_test_async_engine = create_async_engine(settings.db.async_url, pool_size=5)
_TestAsyncSessionLocal = async_sessionmaker(_test_async_engine, expire_on_commit=False)


# ── Database lifecycle ───────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Create tables once per test session; drop them at the end."""
    engine = create_engine(settings.db.sync_url)
    BaseModel.metadata.create_all(engine)
    yield
    BaseModel.metadata.drop_all(engine)
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


# ── Payload helpers ──────────────────────────────────────────────────────────


def make_timer_payload(
    *,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 60,
    url: str = "https://example.com/hook",
) -> dict:
    """Build a valid ``POST /timer`` request body."""
    return {"hours": hours, "minutes": minutes, "seconds": seconds, "url": url}

