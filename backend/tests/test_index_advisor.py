"""Unit tests for index_advisor service and safe DDL generation."""

import pytest

from app.schemas.optimizer import PlanFinding
from app.services.optimizer.index_advisor import (
    advise_indexes,
    generate_safe_ddl,
)


def test_generate_safe_ddl_valid_single_and_composite():
    """Verify DDL formatting with safe quoting and correct naming."""
    name, ddl = generate_safe_ddl("orders", ["created_at"])
    assert name == "ix_orders_created_at"
    assert ddl == 'CREATE INDEX "ix_orders_created_at" ON "orders" ("created_at");'

    comp_name, comp_ddl = generate_safe_ddl("orders", ["status", "created_at"])
    assert comp_name == "ix_orders_status_created_at"
    assert comp_ddl == 'CREATE INDEX "ix_orders_status_created_at" ON "orders" ("status", "created_at");'


def test_generate_safe_ddl_with_partial_predicate():
    """Verify partial index DDL with sanitized WHERE clause."""
    name, ddl = generate_safe_ddl("orders", ["created_at"], predicate="status = 'delivered'")
    assert "ix_orders_created_at_partial" in name
    assert ddl == 'CREATE INDEX "' + name + '" ON "orders" ("created_at") WHERE (status = \'delivered\');'


def test_generate_safe_ddl_rejects_disallowed_table():
    """Verify disallowed or malicious table names are rejected."""
    with pytest.raises(ValueError, match="not an allowed database table"):
        generate_safe_ddl("pg_shadow", ["id"])

    with pytest.raises(ValueError, match="not an allowed database table"):
        generate_safe_ddl("users; DROP TABLE orders; --", ["id"])


def test_generate_safe_ddl_rejects_disallowed_or_injected_column():
    """Verify unknown or SQL-injection column names are rejected."""
    with pytest.raises(ValueError, match="not a valid column"):
        generate_safe_ddl("orders", ["created_at; DROP TABLE users; --"])

    with pytest.raises(ValueError, match="not a valid column"):
        generate_safe_ddl("users", ["password_hash"])



def test_advise_indexes_composite_equality_first():
    """Verify composite index recommendations prioritize equality column before range column."""
    findings = [
        PlanFinding(
            type="seq_scan_large_table",
            severity="critical",
            plan_node="Seq Scan on orders",
            table="orders",
            columns=["created_at", "status"],
            evidence={"filter": "((status = 'delivered') AND (created_at >= '2026-01-01'))"},
            explanation="Sequential scan filtering by status and created_at.",
        )
    ]

    suggestions = advise_indexes(findings)
    assert len(suggestions) >= 1

    # Composite suggestion must have 'status' first, then 'created_at'
    composite = next(s for s in suggestions if s.columns == ["status", "created_at"])
    assert composite.table == "orders"
    assert composite.columns == ["status", "created_at"]
    assert '("status", "created_at")' in composite.ddl
    assert "equality column 'status' first" in composite.reasoning


def test_advise_indexes_deduplication():
    """Verify suggestions are marked as existing when matching catalog."""
    findings = [
        PlanFinding(
            type="seq_scan_large_table",
            severity="critical",
            plan_node="Seq Scan on orders",
            table="orders",
            columns=["created_at"],
            evidence={"filter": "(created_at >= '2026-01-01')"},
            explanation="Seq scan on created_at.",
        )
    ]

    existing_set = {"orders:created_at"}
    suggestions = advise_indexes(findings, existing_indexes=existing_set)
    assert len(suggestions) == 1
    assert suggestions[0].existing is True


def test_advise_indexes_order_items_product_id():
    """Verify recommendation generated for order_items.product_id join bottleneck."""
    findings = [
        PlanFinding(
            type="seq_scan_large_table",
            severity="critical",
            plan_node="Seq Scan on order_items",
            table="order_items",
            columns=["product_id"],
            evidence={"rows_read": 1120000},
            explanation="Seq scan scanning 1.12M line items.",
        )
    ]

    suggestions = advise_indexes(findings)
    assert any(s.table == "order_items" and s.columns == ["product_id"] for s in suggestions)
