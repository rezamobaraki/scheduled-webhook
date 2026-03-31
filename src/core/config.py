"""Application settings loaded from environment variables.

Every setting is overridable via an ``APP_``-prefixed env var.
Example: ``APP_DATABASE_URL=postgresql+asyncpg://...``
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL ── async driver for FastAPI, sync driver for Celery workers.
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/timers"
    )
    sync_database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/timers"
    )

    # Redis ── used as the Celery message broker.
    redis_url: str = "redis://localhost:6379/0"

    # Webhook delivery
    webhook_timeout: int = 10  # seconds per HTTP call
    webhook_max_retries: int = 3  # retries before marking "failed"

    # Recovery sweep interval (seconds).  A Celery Beat task re-dispatches
    # any overdue timers that the broker may have lost.
    sweep_interval: float = 30.0

    model_config = {"env_prefix": "APP_"}


settings = Settings()
