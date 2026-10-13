"""Create query_history table in querypilot_app

Revision ID: 0001_query_history
Revises: 
Create Date: 2026-10-13 07:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_query_history"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="manual", nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_query_history"),
        sa.CheckConstraint(
            "status IN ('success', 'rejected', 'error', 'timeout')",
            name="ck_query_history_status_valid",
        ),
    )
    op.create_index("ix_query_history_created_at", "query_history", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_query_history_created_at", table_name="query_history")
    op.drop_table("query_history")
