"""Integration tests for Celery tasks — requires PostgreSQL via Docker.

Webhook delivery is mocked via ``WebhookService`` — these tests verify the
task → repository → DB round-trip plus retry and sweep logic.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.configs import settings
from src.core.errors import WebhookDeliveryError
from src.enums import TimerStatus
from src.models import Timer

_WEBHOOK_URL = "https://example.com/webhook"


def _insert_timer(
    session: Session,
    *,
    seconds_ago: int = 60,
    status: TimerStatus = TimerStatus.PENDING,
) -> Timer:
    """Insert a timer directly into the database."""
    now = datetime.now(UTC)
    timer = Timer(
        id=uuid.uuid4(),
        url=_WEBHOOK_URL,
        scheduled_at=now - timedelta(seconds=seconds_ago),
        executed_at=now if status == TimerStatus.EXECUTED else None,
        failed_at=now if status == TimerStatus.FAILED else None,
        status=status,
    )
    session.add(timer)
    session.commit()
    session.refresh(timer)
    return timer


# ── fire_webhook ─────────────────────────────────────────────────────────────


class TestFireWebhook:
    """Tests for the ``fire_webhook`` Celery task."""

    @patch("src.worker.tasks.webhook_service")
    def test_calls_url_and_marks_executed(self, mock_service, sync_session):
        """Happy path: webhook succeeds → timer becomes 'executed'."""
        from src.worker.tasks import fire_webhook

        timer = _insert_timer(sync_session)

        fire_webhook.apply(args=[str(timer.id)])

        mock_service.deliver.assert_called_once_with(timer.id, timer.url)
        sync_session.refresh(timer)
        assert timer.status == TimerStatus.EXECUTED
        assert timer.executed_at is not None
        assert timer.failed_at is None
        assert timer.attempt_count == 1
        assert timer.last_error is None

    @patch("src.worker.tasks.webhook_service")
    def test_skips_already_executed_timer(self, mock_service, sync_session):
        """Exactly-once: an executed timer must not trigger a second webhook."""
        from src.worker.tasks import fire_webhook

        timer = _insert_timer(sync_session, status=TimerStatus.EXECUTED)

        fire_webhook.apply(args=[str(timer.id)])

        mock_service.deliver.assert_not_called()

    @patch("src.worker.tasks.webhook_service")
    def test_skips_unknown_timer(self, mock_service):
        """No-op when the timer ID does not exist."""
        from src.worker.tasks import fire_webhook

        fire_webhook.apply(args=[str(uuid.uuid4())])

        mock_service.deliver.assert_not_called()

    @patch("src.worker.tasks.webhook_service")
    def test_retries_then_marks_failed(self, mock_service, sync_session):
        """Webhook failure → task retries, then marks timer 'failed'."""
        from src.worker.tasks import fire_webhook

        timer = _insert_timer(sync_session)
        mock_service.deliver.side_effect = WebhookDeliveryError(
            timer.id, cause=Exception("connection refused"),
        )

        fire_webhook.apply(args=[str(timer.id)])

        # Initial call + retries
        assert mock_service.deliver.call_count == settings.webhook.max_retries + 1

        # After all retries exhausted the timer is marked failed.
        sync_session.refresh(timer)
        assert timer.status == TimerStatus.FAILED
        assert timer.failed_at is not None
        assert timer.executed_at is None
        assert timer.attempt_count >= 1
        assert timer.last_error is not None

    @patch("src.worker.tasks.webhook_service")
    def test_retries_on_http_5xx(self, mock_service, sync_session):
        """HTTP 500 from the webhook target triggers retry."""
        from src.worker.tasks import fire_webhook

        timer = _insert_timer(sync_session)
        mock_service.deliver.side_effect = WebhookDeliveryError(
            timer.id, cause=Exception("Internal Server Error"),
        )

        fire_webhook.apply(args=[str(timer.id)])

        assert mock_service.deliver.call_count == settings.webhook.max_retries + 1
        sync_session.refresh(timer)
        assert timer.status == TimerStatus.FAILED
        assert timer.failed_at is not None
        assert timer.executed_at is None
        assert timer.attempt_count >= 1
        assert timer.last_error is not None

    def test_rejects_inconsistent_executed_state(self, sync_session):
        """The database must reject executed timers without ``executed_at``."""
        timer = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=datetime.now(UTC) - timedelta(seconds=60),
            status=TimerStatus.EXECUTED,
        )

        sync_session.add(timer)

        with pytest.raises(IntegrityError):
            sync_session.commit()

        sync_session.rollback()

    def test_rejects_inconsistent_failed_state(self, sync_session):
        """The database must reject failed timers without ``failed_at``."""
        timer = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=datetime.now(UTC) - timedelta(seconds=60),
            status=TimerStatus.FAILED,
        )

        sync_session.add(timer)

        with pytest.raises(IntegrityError):
            sync_session.commit()

        sync_session.rollback()


# ── sweep_overdue_timers ─────────────────────────────────────────────────────


class TestSweep:
    """Tests for the ``sweep_overdue_timers`` periodic task."""

    @patch("src.worker.tasks.fire_webhook.delay")
    def test_dispatches_overdue_pending_timers(self, mock_delay, sync_session):
        """Sweep should dispatch only overdue pending timers."""
        from src.worker.tasks import sweep_overdue_timers

        t1 = _insert_timer(sync_session, seconds_ago=120)
        t2 = _insert_timer(sync_session, seconds_ago=60)

        # Future timer — must NOT be dispatched
        future = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=datetime.now(UTC) + timedelta(hours=1),
            status=TimerStatus.PENDING,
        )
        sync_session.add(future)
        sync_session.commit()

        sweep_overdue_timers()

        dispatched = {c.args[0] for c in mock_delay.call_args_list}
        assert str(t1.id) in dispatched
        assert str(t2.id) in dispatched
        assert str(future.id) not in dispatched

    @patch("src.worker.tasks.fire_webhook.delay")
    def test_ignores_already_executed(self, mock_delay, sync_session):
        """Sweep must skip timers that have already been executed."""
        from src.worker.tasks import sweep_overdue_timers

        _insert_timer(sync_session, seconds_ago=60, status=TimerStatus.EXECUTED)

        sweep_overdue_timers()

        mock_delay.assert_not_called()

    @patch("src.worker.tasks.fire_webhook.delay")
    def test_ignores_failed_timers(self, mock_delay, sync_session):
        """Sweep must skip timers that are permanently failed."""
        from src.worker.tasks import sweep_overdue_timers

        _insert_timer(sync_session, seconds_ago=60, status=TimerStatus.FAILED)

        sweep_overdue_timers()

        mock_delay.assert_not_called()


# ── dispatch_upcoming_timers ─────────────────────────────────────────────────

class TestDispatcher:
    """Tests for the ``dispatch_upcoming_timers`` windowed dispatcher task."""

    @patch("src.worker.tasks.fire_webhook.apply_async")
    def test_dispatches_upcoming_pending_timers(self, mock_apply, sync_session):
        """Dispatcher should dispatch pending timers due within the window."""
        from src.worker.tasks import dispatch_upcoming_timers

        now = datetime.now(UTC)
        t1 = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=now + timedelta(minutes=2),
            status=TimerStatus.PENDING,
        )
        t2 = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=now + timedelta(minutes=4),
            status=TimerStatus.PENDING,
        )
        sync_session.add_all([t1, t2])
        sync_session.commit()

        dispatch_upcoming_timers()

        dispatched_ids = {c.kwargs["args"][0] for c in mock_apply.call_args_list}
        assert str(t1.id) in dispatched_ids
        assert str(t2.id) in dispatched_ids
        assert mock_apply.call_count == 2

    @patch("src.worker.tasks.fire_webhook.apply_async")
    def test_ignores_far_future_timers(self, mock_apply, sync_session):
        """Dispatcher must skip timers beyond the dispatch window."""
        from src.worker.tasks import dispatch_upcoming_timers

        far_future = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=datetime.now(UTC) + timedelta(hours=2),
            status=TimerStatus.PENDING,
        )
        sync_session.add(far_future)
        sync_session.commit()

        dispatch_upcoming_timers()

        mock_apply.assert_not_called()

    @patch("src.worker.tasks.fire_webhook.apply_async")
    def test_ignores_already_executed(self, mock_apply, sync_session):
        """Dispatcher must skip timers that have already been executed."""
        from src.worker.tasks import dispatch_upcoming_timers

        now = datetime.now(UTC)
        executed = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=now + timedelta(minutes=2),
            status=TimerStatus.EXECUTED,
            executed_at=now,
        )
        sync_session.add(executed)
        sync_session.commit()

        dispatch_upcoming_timers()

        mock_apply.assert_not_called()

    @patch("src.worker.tasks.fire_webhook.apply_async")
    def test_ignores_overdue_timers(self, mock_apply, sync_session):
        """Dispatcher only looks ahead — overdue timers belong to the sweep."""
        from src.worker.tasks import dispatch_upcoming_timers

        overdue = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=5),
            status=TimerStatus.PENDING,
        )
        sync_session.add(overdue)
        sync_session.commit()

        dispatch_upcoming_timers()

        mock_apply.assert_not_called()

    @patch("src.worker.tasks.fire_webhook.apply_async")
    def test_dispatches_with_eta(self, mock_apply, sync_session):
        """Dispatched tasks must carry the timer's ``scheduled_at`` as ETA."""
        from src.worker.tasks import dispatch_upcoming_timers

        scheduled = datetime.now(UTC) + timedelta(minutes=3)
        timer = Timer(
            id=uuid.uuid4(),
            url=_WEBHOOK_URL,
            scheduled_at=scheduled,
            status=TimerStatus.PENDING,
        )
        sync_session.add(timer)
        sync_session.commit()

        dispatch_upcoming_timers()

        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args.kwargs
        assert call_kwargs["eta"] == timer.scheduled_at

