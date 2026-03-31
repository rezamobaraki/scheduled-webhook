"""Create timers table.

Revision ID: 001
Revises: —
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "timers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "in_progress", "executed", "failed", name="timer_status"),
            server_default="pending",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_timers_status_scheduled_at",
        "timers",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_timers_status_scheduled_at", table_name="timers")
    op.drop_table("timers")
    sa.Enum(name="timer_status").drop(op.get_bind(), checkfirst=True)
