"""Secure read-only query executor and audit logging service."""

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as dt_time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.db.models import QueryHistory
from app.db.session import AppAsyncSessionLocal, shop_engine

logger = logging.getLogger(__name__)

TIMEOUT_SQLSTATES = {"57014", "55P03"}  # 57014: query_canceled, 55P03: lock_not_available


class QueryExecutorException(Exception):
    """Base exception for query execution failures."""

    def __init__(self, message: str, duration_ms: float, sqlstate: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.duration_ms = duration_ms
        self.sqlstate = sqlstate


class QueryTimeoutError(QueryExecutorException):
    """Raised when query execution exceeds statement or lock timeout."""


class QueryExecutionError(QueryExecutorException):
    """Raised when query execution fails due to a database-level error."""


@dataclass(frozen=True)
class QueryResult:
    """Outcome of successfully executing a read-only query."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: float
    truncated: bool = False


def _serialize_value(val: Any) -> Any:
    """Format Python / DBAPI values into JSON-serializable primitives."""
    if isinstance(val, (datetime, date, dt_time)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, UUID):
        return str(val)
    if isinstance(val, bytes):
        return val.hex()
    return val


async def execute_readonly_query(
    sanitized_sql: str,
    timeout_ms: int = 5000,
    max_rows: int = 1000,
) -> QueryResult:
    """Execute a sanitized query within an explicit read-only transaction on sample_shop.

    Guarantees:
    - SET TRANSACTION READ ONLY is executed as the very first statement.
    - Strict statement, lock, and idle timeouts are configured per transaction.
    - Executed solely against sample_shop via the isolated readonly_user role.
    - Enforces row capping and formats JSON-safe responses.
    - SQLSTATE-based detection of statement and lock timeouts.

    Args:
        sanitized_sql: AST-regenerated SQL string.
        timeout_ms: Per-statement timeout in milliseconds.
        max_rows: Maximum rows to return before truncating.

    Returns:
        QueryResult with column metadata, rows, row count, duration, and truncation status.

    Raises:
        QueryTimeoutError: If execution exceeds statement or lock timeouts.
        QueryExecutionError: If PostgreSQL rejects or fails query execution.
    """
    duration_ms = 0.0

    async with shop_engine.connect() as conn, conn.begin():
        # 1. Enforce transaction read-only as the initial statement
        await conn.execute(text("SET TRANSACTION READ ONLY;"))
        await conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)};"))
        await conn.execute(text("SET LOCAL lock_timeout = 3000;"))
        await conn.execute(text("SET LOCAL idle_in_transaction_session_timeout = 5000;"))

        # 2. Execute sanitized user query
        exec_start = time.perf_counter()
        try:
            cursor_result = await conn.execute(text(sanitized_sql))
            duration_ms = round((time.perf_counter() - exec_start) * 1000.0, 2)
        except DBAPIError as e:
            duration_ms = round((time.perf_counter() - exec_start) * 1000.0, 2)
            orig = getattr(e, "orig", None)
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)

            clean_msg = str(orig or e).strip()
            if sqlstate in TIMEOUT_SQLSTATES:
                raise QueryTimeoutError(
                    message=f"Query execution timed out after {duration_ms}ms (limit: {timeout_ms}ms)",
                    duration_ms=duration_ms,
                    sqlstate=sqlstate,
                ) from e

            raise QueryExecutionError(
                message=clean_msg,
                duration_ms=duration_ms,
                sqlstate=sqlstate,
            ) from e
        except SQLAlchemyError as e:
            duration_ms = round((time.perf_counter() - exec_start) * 1000.0, 2)
            raise QueryExecutionError(
                message=f"Database execution error: {e}",
                duration_ms=duration_ms,
            ) from e

        # 3. Process and format results
        if not cursor_result.returns_rows:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                duration_ms=duration_ms,
                truncated=False,
            )

        columns = list(cursor_result.keys())
        # Fetch max_rows + 1 to detect if total rows exceed the limit
        raw_rows = cursor_result.mappings().fetchmany(max_rows + 1)
        truncated = len(raw_rows) > max_rows
        final_rows = raw_rows[:max_rows]

        formatted_rows = [{k: _serialize_value(v) for k, v in row.items()} for row in final_rows]

        return QueryResult(
            columns=columns,
            rows=formatted_rows,
            row_count=len(formatted_rows),
            duration_ms=duration_ms,
            truncated=truncated,
        )


async def log_query_history(
    sql_text: str,
    status: str,
    source: str = "manual",
    duration_ms: float | None = None,
    row_count: int | None = None,
    error_message: str | None = None,
    question: str | None = None,
    explanation: str | None = None,
    repaired: bool = False,
    repair_sql: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_latency_ms: int | None = None,
) -> int | None:
    """Record query attempt in querypilot_app database in an independent transaction.

    Failures to write history are logged but will never abort or crash the query response.

    Args:
        sql_text: Raw or sanitized SQL text (capped at 10,000 characters).
        status: Execution status ('success', 'clarification', 'rejected', 'error', 'timeout', 'llm_failure').
        source: Request origin (e.g. 'manual', 'ask', 'agent').
        duration_ms: Duration in milliseconds.
        row_count: Number of rows returned.
        error_message: Error description if failed.
        question: Natural language question asked (for Phase 4/5).
        explanation: LLM-generated explanation.
        repaired: Whether SQL was repaired after an initial validation/execution error.
        repair_sql: The original SQL prior to repair (if repaired).
        llm_provider: LLM provider name (e.g. 'openai').
        llm_model: LLM model name (e.g. 'gpt-4o-mini').
        llm_latency_ms: Latency of LLM invocation in milliseconds.

    Returns:
        The created history row ID, or None if logging failed.
    """
    try:
        async with AppAsyncSessionLocal() as session:
            entry = QueryHistory(
                source=source[:50],
                sql_text=sql_text[:10000],
                status=status,
                duration_ms=Decimal(str(round(duration_ms, 2)))
                if duration_ms is not None
                else None,
                row_count=row_count,
                error_message=error_message[:2000] if error_message else None,
                question=question[:2000] if question else None,
                explanation=explanation[:4000] if explanation else None,
                repaired=repaired,
                repair_sql=repair_sql[:10000] if repair_sql else None,
                llm_provider=llm_provider[:50] if llm_provider else None,
                llm_model=llm_model[:100] if llm_model else None,
                llm_latency_ms=llm_latency_ms,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry.id
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to persist query audit log to querypilot_app: %s", exc)
        return None
