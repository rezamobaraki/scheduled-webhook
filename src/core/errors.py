"""Custom exception classes and FastAPI exception handlers.

Register handlers via :func:`register_exception_handlers` during app startup.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class TimerNotFoundError(Exception):
    """Raised when a timer lookup returns no result."""

    def __init__(self, timer_id: str) -> None:
        self.timer_id = timer_id
        super().__init__(f"Timer {timer_id} not found.")


def register_exception_handlers(app: FastAPI) -> None:
    """Attach custom JSON error handlers to the FastAPI application."""

    @app.exception_handler(TimerNotFoundError)
    async def _timer_not_found(request: Request, exc: TimerNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": str(exc), "code": "TIMER_NOT_FOUND"},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "loc": list(e.get("loc", [])),
                "msg": e.get("msg", ""),
                "type": e.get("type", ""),
            }
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation error",
                "code": "VALIDATION_ERROR",
                "details": details,
            },
        )



