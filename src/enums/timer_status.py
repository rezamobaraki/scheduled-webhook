"""Enumerations shared across the application."""

from enum import StrEnum


class TimerStatus(StrEnum):
    """Lifecycle states of a :class:`Timer`.

    ``PENDING`` → ``IN_PROGRESS`` → ``EXECUTED`` | ``FAILED``
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    EXECUTED = "executed"
    FAILED = "failed"

