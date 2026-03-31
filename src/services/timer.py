import uuid
from datetime import UTC, datetime, timedelta

from src.core import Logger
from src.core.configs import settings
from src.core.errors import TimerNotFoundError
from src.models import Timer
from src.repository import TimerAsyncInterface
from src.schemas import TimerCreateRequest, TimerCreateResponse, TimerRetrieveResponse

logger = Logger.get(__name__)


class TimerService:
    __slots__ = ("timer_repository",)

    def __init__(self, timer_repository: TimerAsyncInterface) -> None:
        self.timer_repository = timer_repository

    async def create_timer(self, request: TimerCreateRequest) -> TimerCreateResponse:
        """Create a timer, persist it, and optionally dispatch to broker.

        Timers due within the dispatch window are sent directly to Redis
        with an ETA.  Timers further in the future are only saved to the
        database — the periodic ``dispatch_upcoming_timers`` task will
        pick them up when they fall inside the window.
        """
        scheduled_at = datetime.now(UTC) + timedelta(seconds=request.total_seconds)

        timer = Timer(url=str(request.url), scheduled_at=scheduled_at)
        timer = await self.timer_repository.create(timer)

        # Only dispatch immediately if due within the dispatch window.
        if request.total_seconds <= settings.app.dispatch_window:
            # Lazy import avoids circular deps and simplifies mocking in tests.
            from src.worker.tasks import fire_webhook

            try:
                fire_webhook.apply_async(args=[str(timer.id)], eta=scheduled_at)
            except Exception:
                # Broker down — not fatal.  The sweep will recover this timer.
                logger.warning(
                    f"Broker unreachable — sweep will recover timer {timer.id!s}."
                )

        return TimerCreateResponse(id=timer.id, time_left=request.total_seconds)

    async def retrieve_timer(self, timer_id: uuid.UUID) -> TimerRetrieveResponse:
        timer = await self.timer_repository.get_by_id(timer_id)
        if not timer:
            raise TimerNotFoundError(str(timer_id))
        delta = (timer.scheduled_at - datetime.now(UTC)).total_seconds()
        return TimerRetrieveResponse(id=timer.id, time_left=max(0, int(delta)))
