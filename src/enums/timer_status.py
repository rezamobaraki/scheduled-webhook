from enum import StrEnum


class TimerStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    EXECUTED = "executed"
    FAILED = "failed"
