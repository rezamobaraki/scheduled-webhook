"""Unit tests for ``TimerService`` — no database required.

Uses a fake in-memory repository that satisfies ``TimerAsyncInterface``
via structural typing (Protocol). This proves the Protocol + injection
pattern works and tests business logic in isolation.
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core.errors import TimerNotFoundError
from src.models import Timer
from src.schemas import TimerCreateRequest
from src.services import TimerService


class FakeTimerRepository:
    """In-memory repository satisfying ``TimerAsyncInterface``."""

    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Timer] = {}

    async def create(self, timer: Timer) -> Timer:
        if timer.id is None:
            timer.id = uuid.uuid4()
        self._store[timer.id] = timer
        return timer

    async def get_by_id(self, timer_id: uuid.UUID) -> Timer | None:
        return self._store.get(timer_id)


def _mock_tasks_module() -> SimpleNamespace:
    """Build a fake ``src.worker.tasks`` module with a mocked ``fire_webhook``."""
    mock_task = MagicMock()
    return SimpleNamespace(fire_webhook=mock_task), mock_task


class TestCreateTimer:
    """``TimerService.create_timer`` — business logic only."""

    async def test_creates_timer_and_returns_response(self):
        fake_module, mock_task = _mock_tasks_module()
        with patch.dict("sys.modules", {"src.worker.tasks": fake_module}):
            repo = FakeTimerRepository()
            service = TimerService(timer_repository=repo)
            req = TimerCreateRequest(
                hours=0, minutes=0, seconds=120, url="https://example.com/hook",
            )

            resp = await service.create_timer(req)

            assert resp.time_left == 120
            assert resp.id in repo._store
            mock_task.apply_async.assert_called_once()
            assert repo._store[resp.id].dispatched_at is not None

    async def test_survives_broker_failure(self):
        """Timer is persisted even when the broker is unreachable."""
        fake_module, mock_task = _mock_tasks_module()
        mock_task.apply_async.side_effect = Exception("broker down")
        with patch.dict("sys.modules", {"src.worker.tasks": fake_module}):
            repo = FakeTimerRepository()
            service = TimerService(timer_repository=repo)
            req = TimerCreateRequest(
                hours=0, minutes=0, seconds=60, url="https://example.com/hook",
            )

            resp = await service.create_timer(req)

            assert resp.id in repo._store  # timer was saved despite broker failure
            # dispatched_at must NOT be stamped when broker fails
            assert repo._store[resp.id].dispatched_at is None

    async def test_zero_delay_returns_zero(self):
        fake_module, _mock_task = _mock_tasks_module()
        with patch.dict("sys.modules", {"src.worker.tasks": fake_module}):
            repo = FakeTimerRepository()
            service = TimerService(timer_repository=repo)
            req = TimerCreateRequest(
                hours=0, minutes=0, seconds=0, url="https://example.com/hook",
            )

            resp = await service.create_timer(req)

            assert resp.time_left == 0

    async def test_far_future_timer_not_dispatched(self):
        """Timers beyond the dispatch window are NOT sent to Redis on create.

        The periodic ``dispatch_upcoming_timers`` task will pick them up
        when they fall inside the window.
        """
        fake_module, mock_task = _mock_tasks_module()
        with patch.dict("sys.modules", {"src.worker.tasks": fake_module}):
            repo = FakeTimerRepository()
            service = TimerService(timer_repository=repo)
            req = TimerCreateRequest(
                hours=1, minutes=0, seconds=0, url="https://example.com/hook",
            )

            resp = await service.create_timer(req)

            assert resp.time_left == 3600
            assert resp.id in repo._store
            mock_task.apply_async.assert_not_called()


class TestRetrieveTimer:
    """``TimerService.retrieve_timer`` — business logic only."""

    async def test_returns_time_left(self):
        repo = FakeTimerRepository()
        timer = Timer(
            id=uuid.uuid4(),
            url="https://example.com",
            scheduled_at=datetime.now(UTC) + timedelta(seconds=300),
        )
        await repo.create(timer)

        service = TimerService(timer_repository=repo)
        resp = await service.retrieve_timer(timer.id)

        assert 298 <= resp.time_left <= 300

    async def test_expired_returns_zero(self):
        repo = FakeTimerRepository()
        timer = Timer(
            id=uuid.uuid4(),
            url="https://example.com",
            scheduled_at=datetime.now(UTC) - timedelta(seconds=60),
        )
        await repo.create(timer)

        service = TimerService(timer_repository=repo)
        resp = await service.retrieve_timer(timer.id)

        assert resp.time_left == 0

    async def test_unknown_id_raises_not_found(self):
        repo = FakeTimerRepository()
        service = TimerService(timer_repository=repo)

        with pytest.raises(TimerNotFoundError):
            await service.retrieve_timer(uuid.uuid4())

