"""Tool to securely validate and execute read-only queries against sample_shop."""

from typing import Any

from pydantic import BaseModel, Field

from app.agent.tools.base import Tool
from app.core.config import settings
from app.services.query_executor import (
    QueryExecutionError,
    QueryTimeoutError,
    execute_readonly_query,
)
from app.services.sql_validator import validate_sql


class ExecuteReadonlyQueryArgs(BaseModel):
    """Arguments for execute_readonly_query tool."""

    sql: str = Field(
        description="The SQL query to validate and execute in a read-only transaction on sample_shop.",
    )


def _truncate_cell(val: Any, max_len: int = 100) -> Any:
    """Truncate excessively long cell values in preview to conserve context."""
    if isinstance(val, str) and len(val) > max_len:
        return f"{val[:max_len]}..."
    return val


async def handle_execute_readonly_query(args: ExecuteReadonlyQueryArgs) -> dict[str, Any]:
    """Validate and execute read-only query returning capped preview of rows."""
    validation = validate_sql(args.sql)
    if not validation.ok or not validation.sanitized_sql:
        return {
            "ok": False,
            "error": f"SQL validation rejected: {validation.reason}",
        }

    try:
        query_res = await execute_readonly_query(
            sanitized_sql=validation.sanitized_sql,
            timeout_ms=5000,
            max_rows=1000,
        )
    except QueryTimeoutError as err:
        return {
            "ok": False,
            "error": f"Query execution timed out: {err.message}",
            "duration_ms": err.duration_ms,
        }
    except QueryExecutionError as err:
        return {
            "ok": False,
            "error": f"Database execution error: {err.message}",
            "duration_ms": err.duration_ms,
        }

    preview_rows: list[dict[str, Any]] = []
    if settings.agent_send_row_preview:
        capped = query_res.rows[:20]
        preview_rows = [
            {k: _truncate_cell(v) for k, v in row.items()}
            for row in capped
        ]

    return {
        "ok": True,
        "columns": query_res.columns,
        "rows": preview_rows,
        "row_count": query_res.row_count,
        "truncated": query_res.truncated,
        "duration_ms": query_res.duration_ms,
        "sanitized_sql": validation.sanitized_sql,
    }


execute_readonly_query_tool = Tool(
    name="execute_readonly_query",
    description="Validate and execute a read-only SQL query against the e-commerce database. Returns columns, a preview of up to 20 rows, row count, and execution time.",
    args_schema=ExecuteReadonlyQueryArgs,
    handler=handle_execute_readonly_query,
)
