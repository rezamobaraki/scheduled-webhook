"""Response schema for timer creation."""

import uuid

from src.core.responses import BaseResponse


class TimerCreateResponse(BaseResponse):
    """Response of ``POST /timer``."""

    id: uuid.UUID
    time_left: int

