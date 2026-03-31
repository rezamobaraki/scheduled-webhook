import uuid
from datetime import datetime
from typing import ClassVar

from sqlalchemy import TIMESTAMP, Enum, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.enums import TimerStatus
from src.models.base import BaseModel
from src.models.state_mixin import StateMixin


class Timer(StateMixin, BaseModel):
    __tablename__ = "timers"
    __table_args__ = (Index("ix_timers_status_scheduled_at", "status", "scheduled_at"),)

    _state_field = "status"
    _allowed_transitions: ClassVar[dict[TimerStatus, set[TimerStatus]]] = {
        TimerStatus.PENDING: {TimerStatus.EXECUTED, TimerStatus.FAILED},
    }

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        default=uuid.uuid7,
    )

    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    scheduled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )

    executed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
    )

    status: Mapped[TimerStatus] = mapped_column(
        Enum(
            TimerStatus,
            name="timer_status",
            values_callable=lambda status_enum: [status.value for status in status_enum],
            validate_strings=True,
        ),
        default=TimerStatus.PENDING,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Timer id={self.id!s} status={self.status}>"
