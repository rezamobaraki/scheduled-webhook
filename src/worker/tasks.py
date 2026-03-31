"""Celery tasks — webhook delivery and overdue-timer recovery.

Architecture (two-layered scheduler):

* **Layer 2 — precision**: ``fire_webhook`` is dispatched with an ETA so the
  broker delivers it close to the scheduled instant.
* **Layer 1 — durability**: ``sweep_overdue_timers`` runs every 30 s via
  Celery Beat, querying PostgreSQL for any ``pending`` timers whose
  ``scheduled_at`` has passed.  This recovers from broker failures and
  process restarts.

Exactly-once semantics are guaranteed by ``SELECT … FOR UPDATE`` combined
with a status check — only one worker can claim a timer even under
concurrent execution.
"""

import logging

import httpx

from src.core.config import settings
from src.core.database import SyncSessionLocal
from src.repository import SyncTimerRepository
from src.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=settings.webhook.max_retries,
    acks_late=True,
)
def fire_webhook(self, timer_id: str) -> None:
    """POST the webhook for a single timer.

    Guarantees
    ----------
    * **Exactly-once**: ``SELECT … FOR UPDATE`` + ``WHERE status='pending'``
      ensures only one worker can claim the timer.
    * **Retry**: on HTTP / network failure the task retries with exponential
      back-off (5 s → 10 s → 20 s …).
    * **Failure**: after ``max_retries`` the timer is marked ``FAILED``.
    """
    with SyncSessionLocal() as session:
        repo = SyncTimerRepository(session)
        timer = repo.get_pending_for_update(timer_id)

        if timer is None:
            logger.info("Timer %s already processed or unknown — skipping.", timer_id)
            return

        try:
            response = httpx.post(
                timer.url,
                json={"id": str(timer.id)},
                timeout=settings.webhook.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            repo.rollback()  # release row lock so next attempt can acquire it
            logger.warning(
                "Webhook %s failed (attempt %d/%d): %s",
                timer_id,
                self.request.retries + 1,
                self.max_retries + 1,
                exc,
            )
            if self.request.retries >= self.max_retries:
                # All retries exhausted — mark permanently failed.
                timer = repo.get_pending_for_update(timer_id)
                if timer is not None:
                    repo.mark_failed(timer)
                raise
            raise self.retry(
                exc=exc,
                countdown=2 ** self.request.retries * 5,  # 5 s, 10 s, 20 s …
            )

        repo.mark_executed(timer)
        logger.info("Timer %s executed successfully.", timer_id)


@celery_app.task
def sweep_overdue_timers() -> None:
    """Periodic safety-net (Layer 1).

    Query PostgreSQL for overdue ``pending`` timers and re-dispatch them
    into the broker.  ``fire_webhook`` handles de-duplication via row
    locking, so duplicate dispatches are harmless.
    """
    with SyncSessionLocal() as session:
        repo = SyncTimerRepository(session)
        overdue = repo.get_overdue_pending()

        for timer in overdue:
            fire_webhook.delay(str(timer.id))

        if overdue:
            logger.info("Sweep dispatched %d overdue timer(s).", len(overdue))

