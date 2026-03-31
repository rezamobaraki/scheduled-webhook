from pydantic import computed_field
from pydantic_settings import SettingsConfigDict

from src.core.configs.base import BaseConfig


class DatabaseSettings(BaseConfig):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    host: str
    port: int = 5432
    user: str
    password: str
    db: str

    # Connection pool (async engine — FastAPI)
    pool_size: int = 5
    max_overflow: int = 5

    # Connection pool (sync engine — Celery)
    pool_size_sync: int = 2
    max_overflow_sync: int = 3

    @computed_field
    @property
    def async_url(self) -> str:
        """``asyncpg`` URL used by FastAPI request handlers."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )

    @computed_field
    @property
    def sync_url(self) -> str:
        """``psycopg`` URL used by Celery worker tasks."""
        return (
            f"postgresql+psycopg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )
