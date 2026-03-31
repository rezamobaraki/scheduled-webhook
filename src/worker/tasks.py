"""Celery tasks — webhook delivery and overdue-timer recovery.

Architecture (two-layered scheduler):

* **Layer 2 — precision**: ``fire_webhook`` is dispatched with an ETA so the
  broker delivers it close to the scheduled instant.
* **Layer 1 — durability**: ``sweep_overdue_timers`` runs every 30 s via
  Celery Beat, querying Postgresql for any ``pending`` timers whose
  ``scheduled_at`` has passed.  This recovers from broker failures and
  process restarts.

Exactly-once semantics are guaranteed by ``SELECT … FOR UPDATE`` combined
with a status check — only one worker can claim a timer even under
concurrent execution.
"""

import uuid
from datetime import UTC, datetime

from src.core import Logger
from src.core.configs import settings
from src.core.database import SyncSessionLocal
from src.core.errors import WebhookDeliveryError
from src.enums import TimerStatus
from src.repository import SyncTimerRepository, TimerSyncInterface
from src.services.webhook import WebhookService
from src.worker.celery_app import celery_app

logger = Logger.get(__name__)

webhook_service = WebhookService()


@celery_app.task(
    bind=True,
    max_retries=settings.webhook.max_retries,
    acks_late=True,
)
def fire_webhook(self, timer_id: str) -> None:
    """Claim a pending timer, deliver the webhook, and finalise state.

    Guarantees
    ----------
    * **Exactly-once**: ``SELECT … FOR UPDATE`` + ``WHERE status='pending'``
      ensures only one worker can claim the timer.
    * **Retry**: on delivery failure the task retries with exponential
      back-off (5 s → 10 s → 20 s …).
    * **Failure**: after ``max_retries`` the timer is marked ``FAILED``.
    """

    with SyncSessionLocal() as session:
        timer_repository: TimerSyncInterface = SyncTimerRepository(session)
        timer = timer_repository.get_pending_for_update(uuid.UUID(timer_id))

        if timer is None:
            logger.info(f"Timer {timer_id} already processed or unknown - skipping.")
            return

        # ── Claim ────────────────────────────────────────────────────
        timer.transition_to(TimerStatus.PROCESSING)
        timer.attempt_count = self.request.retries + 1
        session.commit()

        # ── Deliver ──────────────────────────────────────────────────
        try:
            webhook_service.deliver(timer.id, timer.url)
        except WebhookDeliveryError as exc:
            logger.warning(
                f"Webhook {timer_id} failed"
                f" (attempt {self.request.retries + 1}/{self.max_retries + 1}): {exc}"
            )
            timer.last_error = str(exc)[:4096]
            if self.request.retries >= self.max_retries:
                timer.transition_to(TimerStatus.FAILED)
                timer.failed_at = datetime.now(UTC)
                session.commit()
                raise exc from None
            session.commit()
            raise self.retry(
                exc=exc,
                countdown=2**self.request.retries * 5,
            ) from exc

        # ── Finalise ─────────────────────────────────────────────────
        timer.transition_to(TimerStatus.EXECUTED)
        timer.executed_at = datetime.now(UTC)
        timer.last_error = None
        session.commit()
        logger.info(f"Timer {timer_id} executed successfully.")


@celery_app.task
def sweep_overdue_timers() -> None:
    """Periodic safety-net (Layer 1).

    Query Postgresql for overdue ``pending`` / ``processing`` timers and
    re-dispatch them into the broker.  ``fire_webhook`` handles
    de-duplication via row locking, so duplicate dispatches are harmless.
    """
    with SyncSessionLocal() as session:
        timer_repository: TimerSyncInterface = SyncTimerRepository(session)
        now = datetime.now(UTC)
        overdue = timer_repository.get_overdue_for_update(now)

        for timer in overdue:
            fire_webhook.delay(str(timer.id))

        if overdue:
            logger.info(f"Sweep dispatched {len(overdue)} overdue timer(s).")
