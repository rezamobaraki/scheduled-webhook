from pydantic import computed_field
from pydantic_settings import SettingsConfigDict
from sqlalchemy import URL

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

    # Shared pool settings
    pool_pre_ping: bool = True
    pool_recycle: int = 1800  # seconds — recycle connections older than 30 min
    pool_timeout: int = 30  # seconds to wait for a connection from the pool

    # Debug — log every SQL statement (never enable in production)
    echo: bool = False

    @computed_field
    @property
    def async_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.db,
        )

    @computed_field
    @property
    def sync_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.db,
        )
