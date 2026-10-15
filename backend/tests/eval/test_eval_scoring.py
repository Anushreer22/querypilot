"""Unit tests for the evaluation comparator and result-set scoring engine."""

from datetime import date, datetime
from decimal import Decimal

from tests.eval.comparator import compare_result_sets, normalize_cell


def test_normalize_cell_primitives() -> None:
    assert normalize_cell(None) is None
    assert normalize_cell("test") == "test"
    assert normalize_cell(42) == 42
    assert normalize_cell(129.994) == 129.99
    assert normalize_cell(129.996) == 130.0
    assert normalize_cell(Decimal("45.678")) == 45.68
    assert normalize_cell(date(2026, 10, 10)) == "2026-10-10"
    assert normalize_cell(datetime(2026, 10, 10, 12, 0, 0)) == "2026-10-10T12:00:00"


def test_comparator_ignores_column_aliases() -> None:
    actual = [
        {"prod_name": "Laptop", "rev": 1200.50},
        {"prod_name": "Mouse", "rev": 50.00},
    ]
    reference = [
        {"name": "Laptop", "total_revenue": 1200.50},
        {"name": "Mouse", "total_revenue": 50.00},
    ]

    ok, reason = compare_result_sets(actual, reference, order_sensitive=True)
    assert ok is True
    assert "Exact result set match" in reason


def test_comparator_normalizes_unsorted_rows() -> None:
    actual = [
        {"id": 2, "name": "Bob"},
        {"id": 1, "name": "Alice"},
    ]
    reference = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    # When order_sensitive is False, row order difference is normalized
    ok_unordered, _ = compare_result_sets(actual, reference, order_sensitive=False)
    assert ok_unordered is True

    # When order_sensitive is True, row order difference causes mismatch
    ok_ordered, reason = compare_result_sets(actual, reference, order_sensitive=True)
    assert ok_ordered is False
    assert "Data mismatch" in reason


def test_comparator_rounds_floats() -> None:
    actual = [{"avg_price": 19.999}]
    reference = [{"avg_price": 20.00}]

    ok, _ = compare_result_sets(actual, reference)
    assert ok is True


def test_comparator_detects_row_count_mismatch() -> None:
    actual = [{"id": 1}]
    reference = [{"id": 1}, {"id": 2}]

    ok, reason = compare_result_sets(actual, reference)
    assert ok is False
    assert "Row count mismatch" in reason
