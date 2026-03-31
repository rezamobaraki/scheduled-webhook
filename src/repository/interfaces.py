import uuid
from datetime import datetime
from typing import Protocol

from src.models import Timer


class TimerAsyncInterface(Protocol):
    async def create(self, timer: Timer) -> Timer: ...

    async def get_by_id(self, timer_id: uuid.UUID) -> Timer | None: ...


class TimerSyncInterface(Protocol):
    def get_pending_for_update(self, timer_id: uuid.UUID) -> Timer | None: ...

    def get_overdue_pending_for_update(
        self,
        now: datetime,
        limit: int = 500,
    ) -> list[Timer]: ...


    def flush(self) -> None: ...

    def rollback(self) -> None: ...
