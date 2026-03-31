from dataclasses import dataclass

from src.core.configs.app import AppSettings
from src.core.configs.database import DatabaseSettings
from src.core.configs.redis import RedisSettings
from src.core.configs.webhook import WebhookSettings

__all__ = (
    "AppSettings",
    "DatabaseSettings",
    "RedisSettings",
    "Settings",
    "WebhookSettings",
    "settings",
)


@dataclass(frozen=True)
class Settings:
    app: AppSettings
    database: DatabaseSettings
    redis: RedisSettings
    webhook: WebhookSettings


settings = Settings(
    app=AppSettings(),
    database=DatabaseSettings(),
    redis=RedisSettings(),
    webhook=WebhookSettings(),
)
