"""Result set comparator for SQL evaluation.

Scores accuracy by comparing result tuples, ignoring column aliases,
rounding floats to 2 decimal places, and normalizing row order when unsorted.
"""

import math
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def normalize_cell(value: Any) -> Any:
    """Normalize a single cell value for comparison."""
    if value is None:
        return None
    if isinstance(value, (float, Decimal)):
        # Treat NaNs and Infs
        if math.isnan(value):
            return "NaN"
        return round(float(value), 2)
    if isinstance(value, (datetime, date)):
        # Standardize dates to ISO string representation
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return tuple(normalize_cell(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, normalize_cell(v)) for k, v in value.items()))
    return value


def _safe_sort_key(item: tuple[Any, ...]) -> tuple[tuple[str, str], ...]:
    """Generate a deterministic sort key that handles None and mixed types safely."""
    key = []
    for val in item:
        if val is None:
            key.append(("0_none", ""))
        elif isinstance(val, (int, float)):
            key.append(("1_num", f"{val:+025.4f}"))
        elif isinstance(val, str):
            key.append(("2_str", val))
        else:
            key.append(("3_other", str(val)))
    return tuple(key)


def normalize_result_rows(
    rows: Sequence[Sequence[Any] | dict[str, Any]],
    order_sensitive: bool = False,
) -> list[tuple[Any, ...]]:
    """Convert result set rows into a normalized list of value tuples.

    Ignores column names / aliases and extracts values in original order.
    """
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        if isinstance(row, dict):
            # Extract row values in column declaration order (ignoring keys)
            tuple_val = tuple(normalize_cell(v) for v in row.values())
        else:
            tuple_val = tuple(normalize_cell(v) for v in row)
        normalized.append(tuple_val)

    if not order_sensitive:
        normalized.sort(key=_safe_sort_key)

    return normalized


def compare_result_sets(
    actual_rows: Sequence[Sequence[Any] | dict[str, Any]],
    reference_rows: Sequence[Sequence[Any] | dict[str, Any]],
    order_sensitive: bool = False,
) -> tuple[bool, str]:
    """Compare two query execution outputs.

    Returns:
        (matches: bool, explanation: str)
    """
    if len(actual_rows) != len(reference_rows):
        return (
            False,
            f"Row count mismatch: generated query produced {len(actual_rows)} rows, reference query produced {len(reference_rows)} rows.",
        )

    norm_actual = normalize_result_rows(actual_rows, order_sensitive=order_sensitive)
    norm_reference = normalize_result_rows(reference_rows, order_sensitive=order_sensitive)

    for idx, (act, ref) in enumerate(zip(norm_actual, norm_reference)):
        if len(act) != len(ref):
            return (
                False,
                f"Column count mismatch at row {idx + 1}: generated has {len(act)} columns, reference has {len(ref)} columns.",
            )

        if act != ref:
            return (
                False,
                f"Data mismatch at row {idx + 1}: generated values {act} != reference values {ref}.",
            )

    return True, "Exact result set match"
