import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.enums import TimerStatus
from src.models.base import BaseModel


class Timer(BaseModel):
    """A one-shot scheduled webhook.

    Attributes
    ----------
    id : UUID
        Unique timer identity returned to the client on creation.
    url : str
        Target URL that receives a ``POST`` when the timer fires.
    scheduled_at : datetime
        UTC instant at which the webhook should fire.
    created_at : datetime
        UTC instant when the timer was created (server-side default).
    executed_at : datetime | None
        UTC instant the webhook was actually delivered (``None`` until executed).
    status : TimerStatus
        Current lifecycle state: ``PENDING`` | ``IN_PROGRESS`` | ``EXECUTED`` | ``FAILED``.
    """

    __tablename__ = "timers"
    __table_args__ = (
        # Composite index powers the periodic sweep query:
        #   SELECT … WHERE status = 'pending' AND scheduled_at <= now()
        Index("ix_timers_pending_scheduled", "status", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"),
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[TimerStatus] = mapped_column(
        Enum(TimerStatus), default=TimerStatus.PENDING,
    )

    def __repr__(self) -> str:
        return f"<Timer id={self.id!s} status={self.status}>"

