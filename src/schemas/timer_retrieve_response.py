import uuid

from src.core.responses import BaseResponse


class TimerRetrieveResponse(BaseResponse):
    """Response of ``GET /timer/{timer_id}``."""

    id: uuid.UUID
    time_left: int
