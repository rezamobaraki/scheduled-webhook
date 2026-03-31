from enum import StrEnum


class TimerStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    EXECUTED = "executed"
    FAILED = "failed"
