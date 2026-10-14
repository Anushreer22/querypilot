"""Tool to inspect query execution plan using plain EXPLAIN (FORMAT JSON)."""

import json
from typing import Any

from pydantic import BaseModel, Field

from app.agent.tools.base import Tool
from app.services.query_executor import (
    QueryExecutionError,
    QueryTimeoutError,
    execute_readonly_query,
)
from app.services.sql_validator import validate_sql


class ExplainQueryArgs(BaseModel):
    """Arguments for explain_query tool."""

    sql: str = Field(
        description="The candidate SQL query to inspect with plain EXPLAIN (FORMAT JSON). NO ANALYZE is performed.",
    )


def _walk_for_seq_scan(plan_node: dict[str, Any]) -> bool:
    """Recursively check whether any node in the execution plan is a Seq Scan."""
    if plan_node.get("Node Type") == "Seq Scan":
        return True
    for sub_plan in plan_node.get("Plans", []):
        if isinstance(sub_plan, dict) and _walk_for_seq_scan(sub_plan):
            return True
    return False


async def handle_explain_query(args: ExplainQueryArgs) -> dict[str, Any]:
    """Validate query and execute plain EXPLAIN (FORMAT JSON) without query execution."""
    validation = validate_sql(args.sql)
    if not validation.ok or not validation.sanitized_sql:
        return {
            "ok": False,
            "error": f"SQL validation rejected: {validation.reason}",
        }

    explain_sql = f"EXPLAIN (FORMAT JSON) {validation.sanitized_sql}"

    try:
        query_res = await execute_readonly_query(
            sanitized_sql=explain_sql,
            timeout_ms=5000,
            max_rows=10,
        )
    except QueryTimeoutError as err:
        return {
            "ok": False,
            "error": f"Explain timed out: {err.message}",
        }
    except QueryExecutionError as err:
        return {
            "ok": False,
            "error": f"Explain execution error: {err.message}",
        }

    if not query_res.rows:
        return {
            "ok": False,
            "error": "PostgreSQL returned no execution plan output",
        }

    first_row = query_res.rows[0]
    raw_plan_data = first_row.get("QUERY PLAN")

    if isinstance(raw_plan_data, str):
        try:
            plan_obj = json.loads(raw_plan_data)
        except json.JSONDecodeError:
            plan_obj = raw_plan_data
    else:
        plan_obj = raw_plan_data

    # PostgreSQL EXPLAIN FORMAT JSON returns a list of plan objects: [{"Plan": {...}}]
    root_plan: dict[str, Any] = {}
    if isinstance(plan_obj, list) and plan_obj:
        root_plan = plan_obj[0].get("Plan", {})
    elif isinstance(plan_obj, dict):
        root_plan = plan_obj.get("Plan", plan_obj)

    node_type = root_plan.get("Node Type", "Unknown")
    total_cost = root_plan.get("Total Cost", 0.0)
    plan_rows = root_plan.get("Plan Rows", 0)
    plan_width = root_plan.get("Plan Width", 0)
    has_seq_scan = _walk_for_seq_scan(root_plan)

    return {
        "ok": True,
        "node_type": node_type,
        "total_cost": total_cost,
        "plan_rows": plan_rows,
        "plan_width": plan_width,
        "has_seq_scan": has_seq_scan,
        "summary": f"{node_type} (cost={total_cost}, rows={plan_rows}, seq_scan={has_seq_scan})",
    }


explain_query_tool = Tool(
    name="explain_query",
    description="Inspect the estimated execution plan for a SQL query using plain EXPLAIN (FORMAT JSON). Returns root node type, estimated cost, estimated rows, and whether sequential scans occur. Does NOT run the query.",
    args_schema=ExplainQueryArgs,
    handler=handle_explain_query,
)
