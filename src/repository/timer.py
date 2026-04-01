import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select
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
    for exactly-once delivery, windowed dispatch, and overdue-timer sweeps.
    """

    __slots__ = ("_session",)

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_update(self, timer_id: uuid.UUID) -> Timer | None:
        """Lock and return a timer by PK, or ``None`` if it does not exist.

        Uses ``SELECT … FOR UPDATE`` so concurrent workers compete safely —
        only one will hold the row at a time.  Status checks are done in
        application code (``fire_webhook``) for clarity and robustness.
        """
        return self._session.execute(
            select(Timer).where(Timer.id == timer_id).with_for_update(),
        ).scalar_one_or_none()

    def get_upcoming_pending(
        self,
        now: datetime,
        window_end: datetime,
        limit: int = 500,
    ) -> list[Timer]:
        """Return pending timers whose ``scheduled_at`` falls within the
        dispatch window (``now`` < ``scheduled_at`` <= ``window_end``)
        and that have not already been dispatched to the broker.
        """
        return list(
            self._session.execute(
                select(Timer)
                .where(Timer.status == TimerStatus.PENDING)
                .where(Timer.dispatched_at.is_(None))
                .where(Timer.scheduled_at > now)
                .where(Timer.scheduled_at <= window_end)
                .order_by(Timer.scheduled_at.asc())
                .limit(limit),
            )
            .scalars()
            .all()
        )

    def get_overdue_for_update(
        self,
        now: datetime,
        stale_threshold: int = 120,
        limit: int = 500,
    ) -> list[Timer]:
        """Return up to *limit* overdue timers eligible for re-dispatch.

        Eligible timers are:
        * ``PENDING`` whose ``scheduled_at`` has passed.
        * ``PROCESSING`` whose ``dispatched_at`` is older than
          *stale_threshold* seconds (i.e. likely stuck after a crash).

        ``skip_locked=True`` lets concurrent sweep tasks partition work
        without blocking each other.
        """
        stale_cutoff = now - timedelta(seconds=stale_threshold)
        return list(
            self._session.execute(
                select(Timer)
                .where(Timer.scheduled_at <= now)
                .where(
                    or_(
                        Timer.status == TimerStatus.PENDING,
                        (
                            (Timer.status == TimerStatus.PROCESSING)
                            & (Timer.dispatched_at <= stale_cutoff)
                        ),
                    )
                )
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
