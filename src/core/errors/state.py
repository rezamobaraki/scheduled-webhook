"""State-machine transition error."""

from enum import StrEnum

from fastapi import status

from src.core.errors.base import AppError
from src.enums import ErrorCode


class StateTransitionError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.INVALID_STATE_TRANSITION

    def __init__(self, model: str, current: StrEnum, target: StrEnum) -> None:
        super().__init__(
            f"{model} cannot transition from '{current}' to '{target}'.",
        )

