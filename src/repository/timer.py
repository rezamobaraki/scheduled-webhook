import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.enums import TimerStatus
from src.models import Timer
from src.repository import TimerAsyncInterface, TimerSyncInterface


class TimerRepository(TimerAsyncInterface):
    """Async data-access for Timer entities (FastAPI request path)."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, timer: Timer) -> Timer:
        self._session.add(timer)
        await self._session.flush()
        return timer

    async def get_by_id(self, timer_id: uuid.UUID) -> Timer | None:
        return await self._session.get(Timer, timer_id)


class SyncTimerRepository(TimerSyncInterface):
    """Sync data-access for Timer entities (Celery worker path).

    Provides the specialised queries that workers need: row-level locking
    for exactly-once delivery and overdue-timer sweeps.
    """

    __slots__ = ("_session",)

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_pending_for_update(self, timer_id: uuid.UUID) -> Timer | None:
        """Lock and return a pending timer, or ``None`` if already processed.

        Uses ``SELECT … FOR UPDATE`` so concurrent workers compete safely —
        only one will claim the row.
        """
        return self._session.execute(
            select(Timer)
            .where(Timer.id == timer_id)
            .where(Timer.status == TimerStatus.PENDING)
            .with_for_update(),
        ).scalar_one_or_none()

    def get_overdue_for_update(
        self,
        now: datetime,
        limit: int = 500,
    ) -> list[Timer]:
        """Return up to *limit* pending timers whose scheduled time has passed.

        ``skip_locked=True`` lets concurrent sweep tasks partition work
        without blocking each other.
        """
        return list(
            self._session.execute(
                select(Timer)
                .where(Timer.status.in_([TimerStatus.PENDING, TimerStatus.PROCESSING]))
                .where(Timer.scheduled_at <= now)
                .order_by(Timer.scheduled_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True),
            )
            .scalars()
            .all()
        )

    def flush(self) -> None:
        self._session.flush()

    def rollback(self) -> None:
        self._session.rollback()
