import ipaddress
import re

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from src.core.configs import settings

# Hosts that must never receive webhooks (SSRF protection).
_BLOCKED_HOST_RE = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[?::1]?)$",
    re.IGNORECASE,
)


class TimerCreateRequest(BaseModel):
    hours: int = Field(ge=0, description="Hours component of the delay")
    minutes: int = Field(ge=0, description="Minutes component of the delay")
    seconds: int = Field(ge=0, description="Seconds component of the delay")
    url: HttpUrl = Field(description="Webhook URL that will be POSTed when the timer fires")

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: HttpUrl) -> HttpUrl:
        if len(value) > settings.app.max_url_length:
            msg = f"URL must not exceed {settings.app.max_url_length} characters."
            raise ValueError(msg)

        host = value.host or ""
        if _BLOCKED_HOST_RE.match(host):
            msg = "Webhook URL must not target localhost or loopback addresses."
            raise ValueError(msg)

        try:  # Catch numeric private/reserved IPs (e.g. 10.x.x.x, 192.168.x.x).
            ip = ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            return value  # Not an IP literal — that's fine (it's a hostname).

        if ip.is_private or ip.is_loopback or ip.is_reserved:
            msg = "Webhook URL must not target private or reserved IP addresses."
            raise ValueError(msg)

        return value

    @model_validator(mode="after")
    def validate_total_duration(self) -> TimerCreateRequest:
        if self.total_seconds > settings.app.max_timer_seconds:
            msg = f"Total delay must not exceed {settings.app.max_timer_seconds}s (30 days)."
            raise ValueError(msg)
        return self

    @property
    def total_seconds(self) -> int:
        return self.hours * 3600 + self.minutes * 60 + self.seconds
