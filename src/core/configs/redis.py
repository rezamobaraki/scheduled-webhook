"""Redis broker — env prefix ``REDIS_``."""

from pydantic import computed_field
from pydantic_settings import SettingsConfigDict

from src.core.configs.base import BaseConfig


class RedisSettings(BaseConfig):
    """Redis connection settings."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str
    port: int = 6379
    db: int = 0

    @computed_field
    @property
    def url(self) -> str:
        """Full Redis connection URL."""
        return f"redis://{self.host}:{self.port}/{self.db}"
