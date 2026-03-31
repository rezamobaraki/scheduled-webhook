"""Business logic for timer creation and retrieval.

This layer orchestrates:

* persistence   — via ``TimerRepository``
* task dispatch — via Celery ``fire_webhook``
* DTO mapping   — ``Timer`` model → Pydantic response

The service never imports SQLAlchemy directly — all queries are
delegated to the repository.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core import Logger
from src.core.errors import TimerNotFoundError
from src.models import Timer
from src.repository import TimerRepository
from src.schemas import TimerCreateRequest, TimerCreateResponse, TimerRetrieveResponse

logger = Logger.get(__name__)


class TimerService:
    """Stateless service — one instance per request."""

    __slots__ = ("_repo",)

    def __init__(self, session: AsyncSession) -> None:
        self._repo = TimerRepository(session)

    async def create_timer(self, req: TimerCreateRequest) -> TimerCreateResponse:
        """Create a timer, persist it, and dispatch a Celery task.

        Even if the broker is temporarily unreachable the timer is safe
        in Postgresql — the periodic sweep will recover it.
        """
        total_seconds = req.total_seconds
        scheduled_at = datetime.now(UTC) + timedelta(seconds=total_seconds)

        timer = Timer(url=str(req.url), scheduled_at=scheduled_at)
        timer = await self._repo.create(timer)

        # Lazy import avoids circular deps and simplifies mocking in tests.
        from src.worker.tasks import fire_webhook

        try:
            fire_webhook.apply_async(args=[str(timer.id)], eta=scheduled_at)
        except Exception:
            # Broker down — not fatal.  The sweep will recover this timer.
            logger.warning(
                "Broker unreachable — sweep will recover timer %s.", timer.id,
            )

        return TimerCreateResponse(id=timer.id, time_left=total_seconds)

    async def retrieve_timer(self, timer_id: uuid.UUID) -> TimerRetrieveResponse:
        """Return time remaining for *timer_id*.

        Raises :class:`TimerNotFoundError` if the timer does not exist.
        """
        timer = await self._repo.get_by_id(timer_id)
        if timer is None:
            raise TimerNotFoundError(str(timer_id))

        delta = (timer.scheduled_at - datetime.now(UTC)).total_seconds()
        return TimerRetrieveResponse(id=timer.id, time_left=max(0, int(delta)))

