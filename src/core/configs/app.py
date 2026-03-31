from pydantic_settings import SettingsConfigDict

from src.core.configs.base import BaseConfig


class AppSettings(BaseConfig):
    model_config = SettingsConfigDict(env_prefix="APP_")

    sweep_interval: float = 30.0
