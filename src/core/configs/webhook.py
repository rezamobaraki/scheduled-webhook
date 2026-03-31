"""Webhook delivery — env prefix ``WEBHOOK_``."""

from pydantic_settings import SettingsConfigDict

from src.core.configs.base import BaseConfig


class WebhookSettings(BaseConfig):
    model_config = SettingsConfigDict(env_prefix="WEBHOOK_")

    timeout: int = 10
    max_retries: int = 3
