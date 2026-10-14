"""Tool to inspect database schema for allowed e-commerce tables."""

from typing import Any

from pydantic import BaseModel, Field

from app.agent.tools.base import Tool
from app.services.schema_context import get_schema_context
from app.services.sql_validator import DEFAULT_ALLOWED_TABLES


class InspectSchemaArgs(BaseModel):
    """Arguments for inspect_schema tool."""

    table: str | None = Field(
        default=None,
        description="Optional table name to inspect ('users', 'products', 'orders', 'order_items'). If omitted, returns schema for all allowed tables.",
    )


async def handle_inspect_schema(args: InspectSchemaArgs) -> dict[str, Any]:
    """Execute inspect_schema tool."""
    if args.table:
        table_clean = args.table.lower().strip()
        if table_clean not in DEFAULT_ALLOWED_TABLES:
            return {
                "ok": False,
                "error": f"Table '{args.table}' is unknown or not permitted. Allowed tables are: {sorted(DEFAULT_ALLOWED_TABLES)}",
            }
        schema_text = await get_schema_context(filter_table=table_clean)
        return {
            "ok": True,
            "table": table_clean,
            "schema": schema_text,
        }

    schema_text = await get_schema_context()
    return {
        "ok": True,
        "table": None,
        "schema": schema_text,
    }


inspect_schema_tool = Tool(
    name="inspect_schema",
    description="Inspect the PostgreSQL database schema for available e-commerce tables (columns, data types, primary keys, foreign keys).",
    args_schema=InspectSchemaArgs,
    handler=handle_inspect_schema,
)
