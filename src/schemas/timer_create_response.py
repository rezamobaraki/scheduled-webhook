import uuid

from src.core.responses import BaseResponse


class TimerCreateResponse(BaseResponse):
    id: uuid.UUID
    time_left: int
