import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import Logger
from src.core.errors import TimerNotFoundError
from src.models import Timer
from src.repository import TimerAsyncInterface, TimerRepository
from src.schemas import TimerCreateRequest, TimerCreateResponse, TimerRetrieveResponse

logger = Logger.get(__name__)


class TimerService:
    __slots__ = ("timer_repository",)

    def __init__(self, timer_repository: TimerAsyncInterface) -> None:
        self.timer_repository = timer_repository

    async def create_timer(self, request: TimerCreateRequest) -> TimerCreateResponse:
        """Create a timer, persist it, and dispatch a Celery task.

        Even if the broker is temporarily unreachable the timer is safe
        in Postgresql — the periodic sweep will recover it.
        """
        scheduled_at = datetime.now(UTC) + timedelta(seconds=request.total_seconds)

        timer = Timer(url=str(request.url), scheduled_at=scheduled_at)
        timer = await self.timer_repository.create(timer)

        # Lazy import avoids circular deps and simplifies mocking in tests.
        from src.worker.tasks import fire_webhook

        try:
            fire_webhook.apply_async(args=[str(timer.id)], eta=scheduled_at)
        except Exception:
            # Broker down — not fatal.  The sweep will recover this timer.
            logger.warning(
                "Broker unreachable — sweep will recover timer %s.",
                timer.id,
            )

        return TimerCreateResponse(id=timer.id, time_left=request.total_seconds)

    async def retrieve_timer(self, timer_id: uuid.UUID) -> TimerRetrieveResponse:
        timer = await self.timer_repository.get_by_id(timer_id)
        if timer is None:
            raise TimerNotFoundError(str(timer_id))

        delta = (timer.scheduled_at - datetime.now(UTC)).total_seconds()
        return TimerRetrieveResponse(id=timer.id, time_left=max(0, int(delta)))
