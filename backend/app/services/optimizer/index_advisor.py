"""Application-constructed index advisor generating safe DDL and evidence-based reasoning."""

import logging
import re

from sqlalchemy import text

from app.db.session import shop_engine
from app.schemas.optimizer import IndexSuggestion, PlanFinding
from app.services.sql_validator import DEFAULT_ALLOWED_TABLES

logger = logging.getLogger(__name__)

# Validated database table column catalog for sample_shop
TABLE_COLUMN_CATALOG: dict[str, set[str]] = {
    "users": {"id", "name", "email", "country", "created_at"},
    "products": {"id", "name", "category", "price", "stock", "created_at"},
    "orders": {"id", "user_id", "status", "total_amount", "created_at"},
    "order_items": {"id", "order_id", "product_id", "quantity", "unit_price"},
}


async def get_existing_indexes() -> set[str]:
    """Retrieve set of existing index column signatures on public schema to avoid duplicates."""
    signatures: set[str] = set()
    try:
        async with shop_engine.connect() as conn:
            cursor = await conn.execute(
                text(
                    """
                    SELECT tablename, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public';
                    """
                )
            )
            rows = cursor.fetchall()
            for table, indexdef in rows:
                # Extract columns inside parenthesis: e.g. (created_at) or (order_id, product_id)
                match = re.search(r"\((.+?)\)", indexdef)
                if match:
                    cols = tuple(c.strip().strip('"').lower() for c in match.group(1).split(","))
                    signatures.add(f"{table.lower()}:{','.join(cols)}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch existing database indexes: %s", exc)
    return signatures


def generate_safe_ddl(
    table: str, columns: list[str], predicate: str | None = None
) -> tuple[str, str]:
    """Construct safe CREATE INDEX SQL statement using strictly validated identifiers."""
    table_clean = table.lower().strip()
    if table_clean not in DEFAULT_ALLOWED_TABLES:
        raise ValueError(f"Table '{table}' is not an allowed database table.")

    allowed_cols = TABLE_COLUMN_CATALOG.get(table_clean, set())
    validated_cols: list[str] = []
    for col in columns:
        col_clean = col.lower().strip()
        if col_clean not in allowed_cols:
            raise ValueError(f"Column '{col}' is not a valid column on table '{table}'.")
        validated_cols.append(col_clean)

    pred_tag = "_partial" if predicate else ""
    index_name = f"ix_{table_clean}_{'_'.join(validated_cols)}{pred_tag}"[:63]
    cols_clause = ", ".join(f'"{c}"' for c in validated_cols)
    where_clause = f" WHERE ({predicate})" if predicate else ""

    ddl = f'CREATE INDEX "{index_name}" ON "{table_clean}" ({cols_clause}){where_clause};'
    return index_name, ddl


def advise_indexes(
    findings: list[PlanFinding],
    existing_indexes: set[str] | None = None,
) -> list[IndexSuggestion]:
    """Generate prioritized, evidence-backed index suggestions based on detected plan bottlenecks."""
    existing = existing_indexes or set()
    suggestions: list[IndexSuggestion] = []
    seen_signatures: set[str] = set()

    for finding in findings:
        table = finding.table
        if not table or table not in DEFAULT_ALLOWED_TABLES:
            continue

        cols = finding.columns
        evidence = finding.evidence
        filter_str = str(evidence.get("filter", ""))

        # Case 1: Sequential Scan on orders with created_at and/or status
        if table == "orders":
            has_status = "status" in cols or "status" in filter_str.lower()
            has_created = "created_at" in cols or "created_at" in filter_str.lower()

            if has_status and has_created:
                # Composite index: equality (status) first, then range (created_at)
                sig = "orders:status,created_at"
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    idx_name, ddl = generate_safe_ddl("orders", ["status", "created_at"])
                    suggestions.append(
                        IndexSuggestion(
                            id=idx_name,
                            table="orders",
                            columns=["status", "created_at"],
                            index_type="btree",
                            ddl=ddl,
                            reasoning=(
                                f"Plan {finding.plan_node} discarded {evidence.get('rows_removed_by_filter', 0):,} rows. "
                                "A composite B-Tree index with equality column 'status' first followed by range column 'created_at' "
                                "enables the planner to perform a tight Bitmap/Index Scan."
                            ),
                            estimated_benefit="ESTIMATED: High speedup for filtered chronological order lookups.",
                            estimated_risk="Adds ~15 MB storage per 500k rows; modest INSERT/UPDATE write overhead on orders.",
                            existing=(sig in existing),
                        )
                    )

            if has_created and not (has_status and len(suggestions) > 0):
                sig = "orders:created_at"
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    idx_name, ddl = generate_safe_ddl("orders", ["created_at"])
                    suggestions.append(
                        IndexSuggestion(
                            id=idx_name,
                            table="orders",
                            columns=["created_at"],
                            index_type="btree",
                            ddl=ddl,
                            reasoning=(
                                f"Plan {finding.plan_node} scanned the orders heap table filtering by date. "
                                "Indexing 'created_at' eliminates sequential scans for date ranges, rolling windows, and monthly trends."
                            ),
                            estimated_benefit="ESTIMATED: Converts full sequential scan of 500k orders into an Index Scan.",
                            estimated_risk="Low maintenance cost; standard single-column B-Tree (~11 MB).",
                            existing=(sig in existing),
                        )
                    )

            # Check for common partial index candidate (e.g. status = 'delivered')
            if "status = 'delivered'" in filter_str.lower():
                sig = "orders:created_at:partial_delivered"
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    idx_name, ddl = generate_safe_ddl(
                        "orders", ["created_at"], predicate="status = 'delivered'"
                    )
                    suggestions.append(
                        IndexSuggestion(
                            id=idx_name,
                            table="orders",
                            columns=["created_at"],
                            index_type="btree",
                            predicate="status = 'delivered'",
                            ddl=ddl,
                            reasoning=(
                                "Delivered orders account for a major slice of analytical queries. "
                                "A partial index on (created_at) WHERE status = 'delivered' indexes only delivered rows, "
                                "reducing index footprint while accelerating historical revenue queries."
                            ),
                            estimated_benefit="ESTIMATED: Compact index footprint with instant seeks for delivered orders.",
                            estimated_risk="Only applies when the query specifies WHERE status = 'delivered'.",
                            existing=(sig in existing),
                        )
                    )

        # Case 2: Sequential Scan or Hash on order_items
        elif table == "order_items":
            if "product_id" in cols or "product_id" in filter_str.lower():
                sig = "order_items:product_id"
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    idx_name, ddl = generate_safe_ddl("order_items", ["product_id"])
                    suggestions.append(
                        IndexSuggestion(
                            id=idx_name,
                            table="order_items",
                            columns=["product_id"],
                            index_type="btree",
                            ddl=ddl,
                            reasoning=(
                                f"Foreign key lookup or aggregation on order_items scanned {evidence.get('rows_read', 0):,} rows. "
                                "Indexing 'product_id' accelerates joins between products and sales line items."
                            ),
                            estimated_benefit="ESTIMATED: Eliminates full table scan on 1.12M+ order items during product joins.",
                            estimated_risk="Order items are inserted frequently; indexing adds minor write overhead (~25 MB).",
                            existing=(sig in existing),
                        )
                    )

            if "order_id" in cols or "order_id" in filter_str.lower():
                sig = "order_items:order_id"
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    idx_name, ddl = generate_safe_ddl("order_items", ["order_id"])
                    suggestions.append(
                        IndexSuggestion(
                            id=idx_name,
                            table="order_items",
                            columns=["order_id"],
                            index_type="btree",
                            ddl=ddl,
                            reasoning=(
                                "Joining orders to order_items by 'order_id' currently requires scanning the entire line-item table. "
                                "A B-Tree on order_items(order_id) turns hash or nested loop joins into direct index seeks."
                            ),
                            estimated_benefit="ESTIMATED: Dramatic speedup for fetching line items by order.",
                            estimated_risk="Write overhead on checkout; index size ~25 MB.",
                            existing=(sig in existing),
                        )
                    )

        # Case 3: Sequential Scan on products
        elif table == "products":
            if "category" in cols or "category" in filter_str.lower():
                sig = "products:category"
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    idx_name, ddl = generate_safe_ddl("products", ["category"])
                    suggestions.append(
                        IndexSuggestion(
                            id=idx_name,
                            table="products",
                            columns=["category"],
                            index_type="btree",
                            ddl=ddl,
                            reasoning=(
                                "Category filtering on products scans all merchandise catalog rows. "
                                "Indexing 'category' allows direct index lookups."
                            ),
                            estimated_benefit="ESTIMATED: Converts full product scan into Index Scan.",
                            estimated_risk="Minimal risk on 5,000 product rows; very small index (<1 MB).",
                            existing=(sig in existing),
                        )
                    )

    return suggestions
