"""Compact database schema context generator and TTL in-memory cache."""

import time
from typing import Any

from sqlalchemy import inspect

from app.core.config import settings
from app.db.session import shop_engine
from app.services.sql_validator import DEFAULT_ALLOWED_TABLES

TABLE_DESCRIPTIONS = {
    "users": "Registered customer accounts.",
    "products": "Merchandise catalog items with category and stock.",
    "orders": "Customer purchase orders with status and monetary totals.",
    "order_items": "Purchased line items linking orders to products with quantity and unit price.",
}

STATUS_ENUM_VALUES = (
    "pending",
    "paid",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
)

_cached_schema_text: str | None = None
_cached_tables_data: dict[str, dict[str, Any]] | None = None
_cached_timestamp: float = 0.0


def invalidate_schema_context_cache() -> None:
    """Manually clear the cached schema context."""
    global _cached_schema_text, _cached_tables_data, _cached_timestamp
    _cached_schema_text = None
    _cached_tables_data = None
    _cached_timestamp = 0.0


def format_schema_description(
    tables_data: dict[str, dict[str, Any]],
    filter_table: str | None = None,
) -> str:
    """Convert raw schema metadata into a compact, human-readable text prompt representation."""
    target_table = filter_table.lower().strip() if filter_table else None

    if target_table:
        lines: list[str] = [
            f"DATABASE SCHEMA FOR TABLE '{target_table}' (PostgreSQL 16, public schema only):",
            "",
        ]
    else:
        lines = [
            "DATABASE SCHEMA (PostgreSQL 16, public schema only):",
            "Only the following 4 tables exist. No other tables or schemas are available.",
            "",
        ]

    for table_name in sorted(tables_data.keys()):
        if table_name.lower() not in DEFAULT_ALLOWED_TABLES:
            continue
        if target_table and table_name.lower() != target_table:
            continue

        meta = tables_data[table_name]
        desc = TABLE_DESCRIPTIONS.get(table_name, "")
        lines.append(f"TABLE {table_name}: {desc}")

        pk_cols = set(meta.get("primary_key", []))
        fk_map = {}
        for fk in meta.get("foreign_keys", []):
            referred = fk.get("referred_table")
            for local_col, ref_col in zip(
                fk.get("constrained_columns", []), fk.get("referred_columns", []), strict=False
            ):
                fk_map[local_col] = f"{referred}.{ref_col}"

        for col in meta.get("columns", []):
            col_name = col["name"]
            col_type = col["type"]
            tags: list[str] = []

            if col_name in pk_cols:
                tags.append("PRIMARY KEY")
            if col_name in fk_map:
                tags.append(f"FOREIGN KEY -> {fk_map[col_name]}")
            if not col.get("nullable", True) and col_name not in pk_cols:
                tags.append("NOT NULL")

            if table_name == "orders" and col_name == "status":
                tags.append(f"ENUM: {list(STATUS_ENUM_VALUES)}")

            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"  - {col_name} ({col_type}){tag_str}")

        lines.append("")

    return "\n".join(lines).strip()


async def get_schema_context(force_refresh: bool = False, filter_table: str | None = None) -> str:
    """Fetch compact schema context with in-memory TTL caching.

    Guarantees:
    - Never fetches or transmits row data.
    - Restricted exclusively to allowed business tables (users, products, orders, order_items).
    - Caches result for settings.schema_cache_ttl_seconds.
    """
    global _cached_schema_text, _cached_tables_data, _cached_timestamp
    now = time.monotonic()
    ttl = settings.schema_cache_ttl_seconds

    if not force_refresh and _cached_tables_data is not None and (now - _cached_timestamp) < ttl:
        if filter_table:
            return format_schema_description(_cached_tables_data, filter_table=filter_table)
        if _cached_schema_text is not None:
            return _cached_schema_text

    async with shop_engine.connect() as conn:

        def _inspect_schema(sync_conn) -> dict[str, dict[str, Any]]:
            inspector = inspect(sync_conn)
            table_names = inspector.get_table_names(schema="public")
            schema_data: dict[str, dict[str, Any]] = {}

            for t in sorted(table_names):
                if t.lower() not in DEFAULT_ALLOWED_TABLES:
                    continue

                schema_data[t] = {
                    "columns": [
                        {
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col["nullable"],
                        }
                        for col in inspector.get_columns(t, schema="public")
                    ],
                    "primary_key": inspector.get_pk_constraint(t, schema="public").get(
                        "constrained_columns", []
                    ),
                    "foreign_keys": inspector.get_foreign_keys(t, schema="public"),
                }
            return schema_data

        tables_data = await conn.run_sync(_inspect_schema)

    _cached_tables_data = tables_data
    _cached_schema_text = format_schema_description(tables_data)
    _cached_timestamp = now

    if filter_table:
        return format_schema_description(tables_data, filter_table=filter_table)
    return _cached_schema_text
