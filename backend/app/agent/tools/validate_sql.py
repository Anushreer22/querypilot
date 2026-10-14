"""Tool to validate a SQL query using the strict AST validator."""

from typing import Any

from pydantic import BaseModel, Field

from app.agent.tools.base import Tool
from app.services.sql_validator import validate_sql


class ValidateSqlArgs(BaseModel):
    """Arguments for validate_sql tool."""

    sql: str = Field(
        description="The candidate SQL query to validate against strict read-only AST safety rules.",
    )


async def handle_validate_sql(args: ValidateSqlArgs) -> dict[str, Any]:
    """Execute validate_sql tool without executing on the database."""
    result = validate_sql(args.sql)
    return {
        "ok": result.ok,
        "reason": result.reason,
        "sanitized_sql": result.sanitized_sql,
        "limit_injected": result.limit_injected,
    }


validate_sql_tool = Tool(
    name="validate_sql",
    description="Validate a candidate SQL query against strict security rules (read-only SELECT, table allowlist, function allowlist, single statement). Never executes SQL.",
    args_schema=ValidateSqlArgs,
    handler=handle_validate_sql,
)
