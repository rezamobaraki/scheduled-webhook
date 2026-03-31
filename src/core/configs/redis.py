from pydantic import computed_field
from pydantic_settings import SettingsConfigDict

from src.core.configs.base import BaseConfig


class RedisSettings(BaseConfig):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str
    port: int = 6379
    db: int = 0

    @computed_field
    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"
