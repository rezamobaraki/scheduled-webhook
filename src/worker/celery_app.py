"""Celery application and broker configuration.

Run the worker:

    celery -A src.worker.celery_app:celery_app worker --loglevel=info

Run the beat scheduler (recovery sweep)::

    celery -A src.worker.celery_app:celery_app beat --loglevel=info
"""

from celery import Celery
from celery.signals import worker_init

from src.core.configs import settings
from src.core.logging import Logger


@worker_init.connect
def _on_worker_init(**_kwargs: object) -> None:
    Logger.setup()


celery_app = Celery(
    "timer_service",
    broker=settings.redis.url,
    include=["src.worker.tasks"],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Reliability — acknowledge only *after* the task completes.
    # If a worker crashes mid-flight the message returns to the queue
    # (equivalent to SQS "visibility timeout" pattern).
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Recovery sweep — periodically query Postgresql for overdue
    # pending timers that the broker may have lost during a restart.
    beat_schedule={
        "sweep-overdue-timers": {
            "task": "src.worker.tasks.sweep_overdue_timers",
            "schedule": settings.app.sweep_interval,
        },
    },
)
