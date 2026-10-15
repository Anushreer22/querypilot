"""Query plan analyzer extracting bottlenecks, sequential scans, and execution evidence."""

import json
import logging
import re
from typing import Any

from sqlalchemy import text

from app.db.session import shop_engine
from app.schemas.optimizer import PlanFinding, PlanNode
from app.services.sql_validator import DEFAULT_ALLOWED_TABLES, validate_sql

logger = logging.getLogger(__name__)


class PlanAnalysisError(Exception):
    """Raised when query plan analysis fails."""


def parse_plan_tree(raw_node: dict[str, Any]) -> PlanNode:
    """Recursively parse raw PostgreSQL EXPLAIN JSON dictionary into typed PlanNode."""
    child_plans = [
        parse_plan_tree(sub_plan)
        for sub_plan in raw_node.get("Plans", [])
        if isinstance(sub_plan, dict)
    ]

    return PlanNode(
        node_type=raw_node.get("Node Type", "Unknown"),
        relation_name=raw_node.get("Relation Name"),
        schema=raw_node.get("Schema"),
        alias=raw_node.get("Alias"),
        startup_cost=float(raw_node.get("Startup Cost", 0.0)),
        total_cost=float(raw_node.get("Total Cost", 0.0)),
        plan_rows=float(raw_node.get("Plan Rows", 0.0)),
        plan_width=int(raw_node.get("Plan Width", 0)),
        actual_startup_time=float(raw_node["Actual Startup Time"])
        if "Actual Startup Time" in raw_node
        else None,
        actual_total_time=float(raw_node["Actual Total Time"])
        if "Actual Total Time" in raw_node
        else None,
        actual_rows=float(raw_node["Actual Rows"]) if "Actual Rows" in raw_node else None,
        actual_loops=int(raw_node["Actual Loops"]) if "Actual Loops" in raw_node else None,
        filter=raw_node.get("Filter"),
        rows_removed_by_filter=int(raw_node["Rows Removed by Filter"])
        if "Rows Removed by Filter" in raw_node
        else None,
        index_name=raw_node.get("Index Name"),
        index_cond=raw_node.get("Index Cond"),
        hash_cond=raw_node.get("Hash Cond"),
        join_type=raw_node.get("Join Type"),
        sort_key=raw_node.get("Sort Key") if isinstance(raw_node.get("Sort Key"), list) else None,
        sort_method=raw_node.get("Sort Method"),
        sort_space_used=int(raw_node["Sort Space Used"]) if "Sort Space Used" in raw_node else None,
        sort_space_type=raw_node.get("Sort Space Type"),
        shared_hit_blocks=int(raw_node["Shared Hit Blocks"])
        if "Shared Hit Blocks" in raw_node
        else None,
        shared_read_blocks=int(raw_node["Shared Read Blocks"])
        if "Shared Read Blocks" in raw_node
        else None,
        plans=child_plans,
    )


def extract_columns_from_expression(expr: str | None) -> list[str]:
    """Extract known table column identifiers from PostgreSQL filter/join expressions."""
    if not expr:
        return []
    # Match alphanumeric column identifiers optionally qualified (e.g., o.created_at, status)
    tokens = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", expr)
    known_columns = {
        "id",
        "name",
        "email",
        "country",
        "created_at",
        "category",
        "price",
        "stock",
        "user_id",
        "status",
        "total_amount",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
    }
    extracted = []
    for token in tokens:
        low = token.lower()
        if low in known_columns and low not in extracted:
            extracted.append(low)
    return extracted


def detect_plan_findings(root_node: PlanNode) -> list[PlanFinding]:
    """Traverse execution plan tree and detect performance bottlenecks and evidence."""
    findings: list[PlanFinding] = []

    def _traverse(node: PlanNode):
        table = node.relation_name.lower() if node.relation_name else None
        filter_cols = extract_columns_from_expression(node.filter)

        # 1. Sequential Scan on Large Tables
        if node.node_type == "Seq Scan" and table in DEFAULT_ALLOWED_TABLES:
            rows_removed = node.rows_removed_by_filter or 0
            rows_read = node.actual_rows if node.actual_rows is not None else node.plan_rows
            severity = "critical" if (rows_read > 50000 or rows_removed > 10000) else "warning"

            findings.append(
                PlanFinding(
                    type="seq_scan_large_table",
                    severity=severity,
                    plan_node=node.node_type,
                    table=table,
                    columns=filter_cols,
                    evidence={
                        "table": table,
                        "rows_read": rows_read,
                        "rows_removed_by_filter": rows_removed,
                        "cost": node.total_cost,
                        "filter": node.filter,
                    },
                    explanation=f"Sequential scan on '{table}' read {int(rows_read):,} rows (removed {rows_removed:,} by filter). Missing index.",
                )
            )

        # 2. Heavy Filter Discard
        if node.rows_removed_by_filter and node.rows_removed_by_filter > 1000:
            findings.append(
                PlanFinding(
                    type="rows_removed_filter",
                    severity="warning",
                    plan_node=node.node_type,
                    table=table,
                    columns=filter_cols,
                    evidence={"rows_removed": node.rows_removed_by_filter, "filter": node.filter},
                    explanation=f"{node.node_type} discarded {node.rows_removed_by_filter:,} rows after scan using filter '{node.filter}'.",
                )
            )

        # 3. Row Estimate Mismatch (>10x ratio)
        if node.actual_rows is not None and node.plan_rows > 0:
            act = max(node.actual_rows, 1.0)
            est = max(node.plan_rows, 1.0)
            ratio = max(act / est, est / act)
            if ratio >= 10.0 and max(act, est) >= 500:
                findings.append(
                    PlanFinding(
                        type="row_estimate_mismatch",
                        severity="warning",
                        plan_node=node.node_type,
                        table=table,
                        columns=filter_cols,
                        evidence={
                            "actual_rows": node.actual_rows,
                            "plan_rows": node.plan_rows,
                            "ratio": round(ratio, 2),
                            "mismatch_ratio": round(ratio, 2),
                        },
                        explanation=f"Planner miscalculated row count on {node.node_type} by {ratio:.1f}x ({int(act):,} actual vs {int(est):,} estimated).",
                    )
                )

        # 4. Sort Spills to Disk
        if (node.sort_space_type and node.sort_space_type.lower() == "disk") or (
            node.sort_method and "external" in node.sort_method.lower()
        ):
            findings.append(
                PlanFinding(
                    type="sort_disk_spill",
                    severity="critical",
                    plan_node=node.node_type,
                    table=table,
                    columns=node.sort_key or [],
                    evidence={
                        "sort_space_type": node.sort_space_type,
                        "sort_space_kb": node.sort_space_used,
                        "sort_method": node.sort_method,
                    },
                    explanation=f"Sort spilled to disk ({node.sort_space_type}, {node.sort_space_used} KB). Exceeds work_mem buffer.",
                )
            )

        # 5. Expensive Nested Loops
        if node.node_type == "Nested Loop" and (
            (node.actual_loops and node.actual_loops > 1000) or node.total_cost > 20000
        ):
            findings.append(
                PlanFinding(
                    type="expensive_nested_loop",
                    severity="warning",
                    plan_node=node.node_type,
                    table=table,
                    columns=[],
                    evidence={"actual_loops": node.actual_loops, "total_cost": node.total_cost},
                    explanation=f"Nested loop executed {node.actual_loops or 1} iterations with high total cost ({node.total_cost:.1f}).",
                )
            )

        # 6. High Disk Buffer Reads
        if node.shared_read_blocks and node.shared_read_blocks > 500:
            hits = node.shared_hit_blocks or 0
            reads = node.shared_read_blocks
            findings.append(
                PlanFinding(
                    type="high_disk_buffer_reads",
                    severity="warning" if reads > hits else "info",
                    plan_node=node.node_type,
                    table=table,
                    columns=[],
                    evidence={"shared_read_blocks": reads, "shared_hit_blocks": hits},
                    explanation=f"Heavy disk I/O on {node.node_type}: read {reads:,} blocks from disk ({hits:,} buffer hits).",
                )
            )

        # Recurse child plans
        for child in node.plans:
            _traverse(child)

    _traverse(root_node)
    return findings


async def analyze_query_plan(
    sql: str,
    run_analyze: bool = True,
    timeout_ms: int = 5000,
) -> tuple[str, PlanNode, list[PlanFinding], float, float | None, float]:
    """Validate query, execute EXPLAIN (FORMAT JSON) or EXPLAIN ANALYZE (with rollback), and detect bottlenecks.

    Guarantees:
    - Queries are validated through Phase 3 AST validator.
    - EXPLAIN ANALYZE is wrapped in SET TRANSACTION READ ONLY and ALWAYS rolled back.
    - Zero writes can ever occur.

    Returns:
        (sanitized_sql, root_plan_node, findings, planning_time_ms, execution_time_ms, total_cost)
    """
    validation = validate_sql(sql)
    if not validation.ok or not validation.sanitized_sql:
        raise PlanAnalysisError(f"SQL validation rejected: {validation.reason}")

    sanitized_sql = validation.sanitized_sql

    async with shop_engine.connect() as conn:
        try:
            # Enforce read-only transaction semantics
            await conn.execute(text("SET TRANSACTION READ ONLY;"))
            await conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)};"))
            await conn.execute(text("SET LOCAL lock_timeout = 3000;"))
            await conn.execute(text("SET LOCAL idle_in_transaction_session_timeout = 5000;"))

            if run_analyze:
                explain_stmt = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sanitized_sql}"
            else:
                explain_stmt = f"EXPLAIN (FORMAT JSON) {sanitized_sql}"

            cursor = await conn.execute(text(explain_stmt))
            row = cursor.scalar()
        finally:
            # Invariant: ALWAYS roll back the transaction
            await conn.rollback()

    if isinstance(row, str):
        try:
            plan_data = json.loads(row)
        except json.JSONDecodeError as err:
            raise PlanAnalysisError(f"Failed to parse EXPLAIN output: {err}") from err
    else:
        plan_data = row

    if not isinstance(plan_data, list) or not plan_data:
        raise PlanAnalysisError("Invalid EXPLAIN JSON structure returned by PostgreSQL")

    first_item = plan_data[0]
    raw_root_plan = first_item.get("Plan", {})
    planning_time_ms = float(first_item.get("Planning Time", 0.0))
    execution_time_ms = (
        float(first_item["Execution Time"]) if "Execution Time" in first_item else None
    )
    total_cost = float(raw_root_plan.get("Total Cost", 0.0))

    root_node = parse_plan_tree(raw_root_plan)
    findings = detect_plan_findings(root_node)

    return sanitized_sql, root_node, findings, planning_time_ms, execution_time_ms, total_cost
