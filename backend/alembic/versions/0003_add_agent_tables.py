"""Add agent_runs and agent_actions tables for Phase 5 agent

Revision ID: 0003_agent_tables
Revises: 0002_ask_history
Create Date: 2026-10-13 14:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_agent_tables"
down_revision: str | None = "0002_ask_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create agent_runs table
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("step_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_ms", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0.0"),
        sa.Column("llm_provider", sa.String(length=50), nullable=True),
        sa.Column("llm_model", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('completed', 'clarification', 'step_limit_exceeded', 'timeout', 'repeated_failure', 'error', 'llm_failure')",
            name="ck_agent_runs_status_valid",
        ),
    )
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])

    # 2. Create agent_actions table
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'rejected')",
            name="ck_agent_actions_status_valid",
        ),
    )
    op.create_index("ix_agent_actions_run_id", "agent_actions", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_actions_run_id", table_name="agent_actions")
    op.drop_table("agent_actions")
    op.drop_index("ix_agent_runs_created_at", table_name="agent_runs")
    op.drop_table("agent_runs")
