from pydantic_settings import SettingsConfigDict

from src.core.configs.base import BaseConfig


class AppSettings(BaseConfig):
    model_config = SettingsConfigDict(env_prefix="APP_")

    # ── Two-layered scheduler ─────────────────────────────────────────
    dispatch_window: int = 300  # seconds — timers due within this window are sent to Redis
    dispatch_interval: float = 300.0  # seconds — how often the dispatcher Beat task runs
    sweep_interval: float = 30.0  # seconds — how often the overdue recovery sweep runs

    max_timer_seconds: int = 30 * 24 * 3600  # 30 days
    max_url_length: int = 2048  # must match DB column: String(2048)
