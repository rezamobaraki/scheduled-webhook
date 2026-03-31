import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Enum, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.enums import TimerStatus
from src.models.base import BaseModel


class Timer(BaseModel):
    __tablename__ = "timers"
    __table_args__ = (Index("ix_timers_status_scheduled_at", "status", "scheduled_at"),)

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
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            validate_strings=True,
        ),
        default=TimerStatus.PENDING,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Timer id={self.id!s} status={self.status}>"
