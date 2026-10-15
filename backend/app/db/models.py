from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for application ORM models."""


class QueryHistory(Base):
    """Audit ledger for all attempted SQL queries and execution outcomes."""

    __tablename__ = "query_history"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'clarification', 'rejected', 'error', 'timeout', 'llm_failure')",
            name="ck_query_history_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual", server_default="manual"
    )
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Phase 4: Ask & LLM Audit Fields
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    repaired: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    repair_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentRun(Base):
    """Audit ledger for autonomous agent reasoning loops."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'clarification', 'step_limit_exceeded', 'timeout', 'repeated_failure', 'error', 'llm_failure')",
            name="ck_agent_runs_status_valid",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_duration_ms: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.0"), server_default="0.0"
    )
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    actions: Mapped[list["AgentAction"]] = relationship(
        "AgentAction",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentAction.step_number",
    )


class AgentAction(Base):
    """Action-level audit record for each tool invocation during an agent run."""

    __tablename__ = "agent_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok', 'error', 'rejected')",
            name="ck_agent_actions_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.0"), server_default="0.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="actions")


class OptimizationHistory(Base):
    """Audit ledger for query plan analysis and optimization benchmark runs."""

    __tablename__ = "optimization_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    findings_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    suggestions_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    benchmarked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    baseline_median_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    optimized_median_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    speedup_factor: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    improvement_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duration_ms: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.0"), server_default="0.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
