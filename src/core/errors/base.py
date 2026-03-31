from fastapi import status

from src.enums import ErrorCode


class AppError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
