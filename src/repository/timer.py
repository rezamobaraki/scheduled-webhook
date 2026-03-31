"""Data access layer for Timer entities.

Two repository classes are provided:

* ``TimerRepository``     — async, used by the FastAPI service layer.
* ``SyncTimerRepository`` — sync, used by Celery worker tasks.

Both encapsulate every database query behind a named method so that
SQL logic is never scattered across service or task code.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.models import Timer
from src.enums import TimerStatus


class TimerRepository:
    """Async data-access for Timer entities (FastAPI request path)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, timer: Timer) -> Timer:
        """Persist a new timer and return the refreshed instance."""
        self._session.add(timer)
        await self._session.commit()
        await self._session.refresh(timer)
        return timer

    async def get_by_id(self, timer_id: uuid.UUID) -> Timer | None:
        """Return a timer by its primary key, or ``None``."""
        result = await self._session.execute(
            select(Timer).where(Timer.id == timer_id),
        )
        return result.scalar_one_or_none()


class SyncTimerRepository:
    """Sync data-access for Timer entities (Celery worker path).

    Provides the specialised queries that workers need: row-level locking
    for exactly-once delivery and overdue-timer sweeps.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_pending_for_update(self, timer_id: str) -> Timer | None:
        """Lock and return a pending timer, or ``None`` if already processed.

        Uses ``SELECT … FOR UPDATE`` so that concurrent workers compete
        safely — only one will claim the row.
        """
        return self._session.execute(
            select(Timer)
            .where(Timer.id == timer_id)
            .where(Timer.status == TimerStatus.PENDING)
            .with_for_update(),
        ).scalar_one_or_none()

    def get_overdue_pending(self, limit: int = 500) -> list[Timer]:
        """Return up to *limit* pending timers whose scheduled time has passed."""
        return list(
            self._session.execute(
                select(Timer)
                .where(Timer.status == TimerStatus.PENDING)
                .where(Timer.scheduled_at <= datetime.now(UTC))
                .limit(limit),
            ).scalars().all()
        )

    def mark_executed(self, timer: Timer) -> None:
        """Transition a timer to ``EXECUTED`` and commit."""
        timer.status = TimerStatus.EXECUTED
        timer.executed_at = datetime.now(UTC)
        self._session.commit()

    def mark_failed(self, timer: Timer) -> None:
        """Transition a timer to ``FAILED`` and commit."""
        timer.status = TimerStatus.FAILED
        self._session.commit()

    def rollback(self) -> None:
        """Roll back the current transaction (releases any row locks)."""
        self._session.rollback()

