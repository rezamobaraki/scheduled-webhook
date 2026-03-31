"""Request schema for timer creation."""

from pydantic import BaseModel, Field, HttpUrl, model_validator

# Upper bound: timers cannot be scheduled more than 30 days out.
_MAX_SECONDS = 30 * 24 * 3600


class TimerCreateRequest(BaseModel):


    hours: int = Field(ge=0, description="Hours component of the delay")
    minutes: int = Field(ge=0, description="Minutes component of the delay")
    seconds: int = Field(ge=0, description="Seconds component of the delay")
    url: HttpUrl = Field(description="Webhook URL that will be POSTed when the timer fires")

    @model_validator(mode="after")
    def _validate_total_duration(self) -> TimerCreateRequest:
        if self.total_seconds > _MAX_SECONDS:
            msg = f"Total delay must not exceed {_MAX_SECONDS}s (30 days)."
            raise ValueError(msg)
        return self

    @property
    def total_seconds(self) -> int:
        """Total delay expressed in seconds."""
        return self.hours * 3600 + self.minutes * 60 + self.seconds

