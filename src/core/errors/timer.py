from fastapi import status

from src.core.errors.base import AppError
from src.enums import ErrorCode


class TimerNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.TIMER_NOT_FOUND

    def __init__(self, timer_id: str) -> None:
        self.timer_id = timer_id
        super().__init__(f"Timer {timer_id} not found.")
