from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual", server_default="manual")
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
    repaired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=func.false())
    repair_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
