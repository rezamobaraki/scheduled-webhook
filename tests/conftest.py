"""Shared test helpers — no database or external services required."""


def make_timer_payload(
    *,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 60,
    url: str = "https://example.com/hook",
) -> dict:
    """Build a valid ``POST /timer`` request body."""
    return {"hours": hours, "minutes": minutes, "seconds": seconds, "url": url}

