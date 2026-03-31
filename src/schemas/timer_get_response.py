"""Response schema for timer retrieval."""

import uuid

from src.core.responses import BaseResponse


class TimerGetResponse(BaseResponse):
    """Response of ``GET /timer/{timer_id}``."""

    id: uuid.UUID
    time_left: int

