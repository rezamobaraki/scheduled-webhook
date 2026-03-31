"""Application configuration.

Settings are loaded from environment variables (and ``.env`` file at project root).
Each domain uses its own prefix so variables stay organised::

    POSTGRES_HOST=localhost
    REDIS_PORT=6379
    WEBHOOK_TIMEOUT=10
    APP_SWEEP_INTERVAL=30
"""

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection configuration.

    Env-var prefix: ``POSTGRES_``
    Connection URLs are derived automatically from individual components
    so that credentials are never hard-coded as a monolithic string.
    """

    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_", env_file=".env", extra="ignore",
    )

    host: str
    port: int = 5432
    user: str
    password: str
    db: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_url(self) -> str:
        """``asyncpg`` URL used by FastAPI request handlers."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_url(self) -> str:
        """``psycopg`` URL used by Celery worker tasks."""
        return (
            f"postgresql+psycopg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class RedisSettings(BaseSettings):
    """Redis broker configuration.

    Env-var prefix: ``REDIS_``
    """

    model_config = SettingsConfigDict(
        env_prefix="REDIS_", env_file=".env", extra="ignore",
    )

    host: str
    port: int = 6379
    db: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        """Full Redis connection URL."""
        return f"redis://{self.host}:{self.port}/{self.db}"


class WebhookSettings(BaseSettings):
    """Webhook delivery configuration.

    Env-var prefix: ``WEBHOOK_``
    """

    model_config = SettingsConfigDict(
        env_prefix="WEBHOOK_", env_file=".env", extra="ignore",
    )

    timeout: int = 10
    max_retries: int = 3


class AppSettings(BaseSettings):
    """General application-level settings.

    Env-var prefix: ``APP_``
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", extra="ignore",
    )

    sweep_interval: float = 30.0


class Settings:
    """Root container that groups every domain-specific setting block."""

    app: AppSettings = AppSettings()
    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    webhook: WebhookSettings = WebhookSettings()


settings = Settings()
