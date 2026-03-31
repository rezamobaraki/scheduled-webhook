"""Create timers table.

Revision ID: 001
Revises: —
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "timers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "in_progress", "executed", "failed", name="timerstatus"),
            server_default="pending",
        ),
    )
    op.create_index(
        "ix_timers_pending_scheduled",
        "timers",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_timers_pending_scheduled", table_name="timers")
    op.drop_table("timers")
    sa.Enum(name="timerstatus").drop(op.get_bind(), checkfirst=True)

