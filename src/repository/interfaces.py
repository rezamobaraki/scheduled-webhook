import uuid
from datetime import datetime
from typing import Protocol

from src.models import Timer


class TimerAsyncInterface(Protocol):
    async def create(self, timer: Timer) -> Timer: ...
    async def get_by_id(self, timer_id: uuid.UUID) -> Timer | None: ...


class TimerSyncInterface(Protocol):
    def get_for_update(self, timer_id: uuid.UUID) -> Timer | None: ...
    def get_upcoming_pending(
        self,
        now: datetime,
        window_end: datetime,
        limit: int = 500,
    ) -> list[Timer]: ...
    def get_overdue_for_update(
        self,
        now: datetime,
        stale_threshold: int = 120,
        limit: int = 500,
    ) -> list[Timer]: ...
    def flush(self) -> None: ...
    def rollback(self) -> None: ...
