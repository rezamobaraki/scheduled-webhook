import uuid

from src.core.responses import BaseResponse


class TimerRetrieveResponse(BaseResponse):
    id: uuid.UUID
    time_left: int
