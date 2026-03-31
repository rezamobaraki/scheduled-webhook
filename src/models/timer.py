import uuid
from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Enum,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.enums import TimerStatus
from src.models.base import BaseModel
from src.models.state_mixin import StateMixin


class Timer(StateMixin, BaseModel):
    __tablename__ = "timers"
    __table_args__ = (
        Index("ix_timers_status_scheduled_at", "status", "scheduled_at"),
        CheckConstraint(
            """
            (status = 'pending'    AND executed_at IS NULL AND failed_at IS NULL)
            OR
            (status = 'processing' AND executed_at IS NULL AND failed_at IS NULL)
            OR
            (status = 'executed'   AND executed_at IS NOT NULL AND failed_at IS NULL)
            OR
            (status = 'failed'     AND executed_at IS NULL AND failed_at IS NOT NULL)
            """,
            name="ck_timers_status_timestamp_consistency",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_timers_attempt_count_non_negative",
        ),
    )

    _state_field = "status"
    _allowed_transitions: ClassVar[dict[TimerStatus, set[TimerStatus]]] = {
        TimerStatus.PENDING: {TimerStatus.PROCESSING},
        TimerStatus.PROCESSING: {TimerStatus.EXECUTED, TimerStatus.FAILED},
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
        nullable=True,
    )

    failed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    status: Mapped[TimerStatus] = mapped_column(
        Enum(
            TimerStatus,
            name="timer_status",
            values_callable=lambda status_enum: [status.value for status in status_enum],
            validate_strings=True,
        ),
        default=TimerStatus.PENDING,
        server_default=text("'pending'"),
        nullable=False,
    )

    # ── Operational metadata ─────────────────────────────────────────
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Timer id={self.id} status={self.status.value} "
            f"scheduled_at={self.scheduled_at.isoformat()}>"
        )
