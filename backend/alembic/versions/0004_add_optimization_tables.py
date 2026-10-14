"""Add optimization_history table for Phase 6 optimizer

Revision ID: 0004_optimization_tables
Revises: 0003_agent_tables
Create Date: 2026-10-14 08:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_optimization_tables"
down_revision: str | None = "0003_agent_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "optimization_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("findings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suggestions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("benchmarked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("baseline_median_ms", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("optimized_median_ms", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("speedup_factor", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("improvement_label", sa.String(length=50), nullable=True),
        sa.Column("duration_ms", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_optimization_history_created_at", "optimization_history", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_optimization_history_created_at", table_name="optimization_history")
    op.drop_table("optimization_history")

