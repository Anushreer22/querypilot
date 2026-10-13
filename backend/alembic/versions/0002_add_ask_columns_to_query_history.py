"""Add ask columns and expand status constraint on query_history

Revision ID: 0002_ask_history
Revises: 0001_query_history
Create Date: 2026-10-13 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_ask_history"
down_revision: str | None = "0001_query_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add Phase 4 columns
    op.add_column("query_history", sa.Column("question", sa.Text(), nullable=True))
    op.add_column("query_history", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column(
        "query_history",
        sa.Column("repaired", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("query_history", sa.Column("repair_sql", sa.Text(), nullable=True))
    op.add_column("query_history", sa.Column("llm_provider", sa.String(length=50), nullable=True))
    op.add_column("query_history", sa.Column("llm_model", sa.String(length=100), nullable=True))
    op.add_column("query_history", sa.Column("llm_latency_ms", sa.Integer(), nullable=True))

    # 2. Update status check constraint to include clarification and llm_failure
    op.drop_constraint("ck_query_history_status_valid", "query_history", type_="check")
    op.create_check_constraint(
        "ck_query_history_status_valid",
        "query_history",
        "status IN ('success', 'clarification', 'rejected', 'error', 'timeout', 'llm_failure')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_query_history_status_valid", "query_history", type_="check")
    op.create_check_constraint(
        "ck_query_history_status_valid",
        "query_history",
        "status IN ('success', 'rejected', 'error', 'timeout')",
    )

    op.drop_column("query_history", "llm_latency_ms")
    op.drop_column("query_history", "llm_model")
    op.drop_column("query_history", "llm_provider")
    op.drop_column("query_history", "repair_sql")
    op.drop_column("query_history", "repaired")
    op.drop_column("query_history", "explanation")
    op.drop_column("query_history", "question")
