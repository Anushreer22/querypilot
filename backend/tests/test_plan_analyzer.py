"""Unit and integration tests for plan_analyzer."""

import pytest
from sqlalchemy import text

from app.db.session import shop_engine
from app.schemas.optimizer import PlanNode
from app.services.optimizer.plan_analyzer import (
    PlanAnalysisError,
    analyze_query_plan,
    detect_plan_findings,
    extract_columns_from_expression,
    parse_plan_tree,
)


def test_parse_plan_tree_unit():
    """Verify recursive parsing of raw PostgreSQL EXPLAIN JSON into typed PlanNode."""
    raw_json = {
        "Node Type": "Sort",
        "Startup Cost": 120.5,
        "Total Cost": 150.8,
        "Plan Rows": 100.0,
        "Plan Width": 32,
        "Actual Startup Time": 1.2,
        "Actual Total Time": 2.5,
        "Actual Rows": 95.0,
        "Actual Loops": 1,
        "Sort Key": ["created_at DESC"],
        "Sort Method": "external merge",
        "Sort Space Used": 16384,
        "Sort Space Type": "Disk",
        "Shared Hit Blocks": 45,
        "Shared Read Blocks": 120,
        "Plans": [
            {
                "Node Type": "Seq Scan",
                "Relation Name": "orders",
                "Startup Cost": 0.0,
                "Total Cost": 100.0,
                "Plan Rows": 100.0,
                "Plan Width": 32,
                "Filter": "(status = 'delivered'::text)",
                "Rows Removed by Filter": 5000,
            }
        ],
    }

    node = parse_plan_tree(raw_json)
    assert isinstance(node, PlanNode)
    assert node.node_type == "Sort"
    assert node.sort_space_type == "Disk"
    assert node.sort_space_used == 16384
    assert len(node.plans) == 1
    assert node.plans[0].node_type == "Seq Scan"
    assert node.plans[0].relation_name == "orders"
    assert node.plans[0].rows_removed_by_filter == 5000


def test_extract_columns_from_expression():
    """Test extracting column identifiers from PostgreSQL filter strings."""
    expr1 = "(created_at >= '2026-01-01'::timestamp) AND (status = 'delivered')"
    cols1 = extract_columns_from_expression(expr1)
    assert "created_at" in cols1
    assert "status" in cols1

    expr2 = "(order_items.product_id = products.id)"
    cols2 = extract_columns_from_expression(expr2)
    assert "product_id" in cols2
    assert "id" in cols2


def test_detect_seq_scan_and_filter_discards():
    """Verify detection of Seq Scan on large table and excessive rows discarded by filter."""
    root = PlanNode(
        node_type="Seq Scan",
        relation_name="orders",
        total_cost=25000.0,
        plan_rows=500000.0,
        actual_rows=100.0,
        actual_total_time=120.0,
        filter="(created_at >= '2026-01-01')",
        rows_removed_by_filter=490000,
    )

    findings = detect_plan_findings(root)
    finding_types = [f.type for f in findings]
    assert "seq_scan_large_table" in finding_types
    assert "rows_removed_filter" in finding_types

    seq_finding = next(f for f in findings if f.type == "seq_scan_large_table")
    assert seq_finding.table == "orders"
    assert seq_finding.severity == "critical"
    assert "created_at" in seq_finding.columns


def test_detect_row_estimate_mismatch():
    """Verify detection of >10x planner row estimation errors."""
    root = PlanNode(
        node_type="Index Scan",
        relation_name="users",
        total_cost=50.0,
        plan_rows=10.0,
        actual_rows=1500.0,  # 150x mismatch
    )

    findings = detect_plan_findings(root)
    finding_types = [f.type for f in findings]
    assert "row_estimate_mismatch" in finding_types
    mismatch = next(f for f in findings if f.type == "row_estimate_mismatch")
    assert mismatch.severity == "warning"
    assert mismatch.evidence["mismatch_ratio"] >= 10.0


def test_detect_sort_disk_spill():
    """Verify detection of memory spill to disk during sorting."""
    root = PlanNode(
        node_type="Sort",
        total_cost=8000.0,
        sort_space_type="Disk",
        sort_space_used=32768,
        sort_method="external merge",
    )

    findings = detect_plan_findings(root)
    assert any(f.type == "sort_disk_spill" for f in findings)
    spill = next(f for f in findings if f.type == "sort_disk_spill")
    assert spill.severity == "critical"


def test_detect_expensive_nested_loop():
    """Verify detection of expensive nested loop joins."""
    root = PlanNode(
        node_type="Nested Loop",
        total_cost=45000.0,
        actual_loops=25000,
    )

    findings = detect_plan_findings(root)
    assert any(f.type == "expensive_nested_loop" for f in findings)


def test_detect_high_disk_buffer_reads():
    """Verify detection of low cache hit ratio (high shared read blocks)."""
    root = PlanNode(
        node_type="Seq Scan",
        relation_name="order_items",
        total_cost=15000.0,
        shared_hit_blocks=50,
        shared_read_blocks=5000,  # Read ratio 99%
    )

    findings = detect_plan_findings(root)
    assert any(f.type == "high_disk_buffer_reads" for f in findings)


@pytest.mark.asyncio
async def test_plan_analysis_blocks_insert_from_explain_analyze():
    """CRITICAL SECURITY TEST: Ensure INSERT/UPDATE/DELETE queries are blocked BEFORE reaching EXPLAIN ANALYZE."""
    malicious_sql = (
        "INSERT INTO users (id, name, email) VALUES (999999, 'Hacker', 'hacker@example.com');"
    )

    with pytest.raises(PlanAnalysisError) as exc_info:
        await analyze_query_plan(malicious_sql, run_analyze=True)

    assert "SQL validation rejected" in str(exc_info.value)

    # Prove conclusively that no row was written to users in sample_shop
    async with shop_engine.connect() as conn:
        result = await conn.execute(text("SELECT id FROM users WHERE id = 999999;"))
        assert result.scalar() is None


@pytest.mark.asyncio
async def test_analyze_query_plan_real_shop_db():
    """Integration test: Execute EXPLAIN (ANALYZE, BUFFERS) on live sample_shop read-only database."""
    sql = "SELECT id, total_amount, created_at FROM orders WHERE created_at >= '2026-01-01' ORDER BY created_at DESC LIMIT 50;"

    (
        sanitized_sql,
        root_node,
        findings,
        planning_time,
        execution_time,
        total_cost,
    ) = await analyze_query_plan(sql, run_analyze=True)

    assert "SELECT" in sanitized_sql
    assert isinstance(root_node, PlanNode)
    assert total_cost > 0.0
    assert planning_time >= 0.0
    assert execution_time is not None and execution_time >= 0.0
    assert isinstance(findings, list)
