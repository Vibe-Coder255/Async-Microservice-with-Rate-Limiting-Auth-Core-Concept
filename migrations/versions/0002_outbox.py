"""add outbox table for transactional event publication

Revision ID: 0002_outbox
Revises: 0001_initial
Create Date: 2026-08-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_outbox"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    outbox_status = postgresql.ENUM(
        "pending", "published", "failed", name="outbox_status", create_type=True
    )
    outbox_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "published", "failed", name="outbox_status", create_type=False
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["event_logs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_outbox_status", "outbox", ["status"])
    op.create_index("ix_outbox_user_id", "outbox", ["user_id"])
    op.create_index("ix_outbox_event_type", "outbox", ["event_type"])
    op.create_index("ix_outbox_created_at", "outbox", ["created_at"])
    op.create_index("ix_outbox_event_id", "outbox", ["event_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_outbox_event_id", table_name="outbox")
    op.drop_index("ix_outbox_created_at", table_name="outbox")
    op.drop_index("ix_outbox_event_type", table_name="outbox")
    op.drop_index("ix_outbox_user_id", table_name="outbox")
    op.drop_index("ix_outbox_status", table_name="outbox")
    op.drop_table("outbox")
    postgresql.ENUM(name="outbox_status").drop(op.get_bind(), checkfirst=True)
