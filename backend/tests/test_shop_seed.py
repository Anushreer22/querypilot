import psycopg

from app.core.config import settings
from scripts.seed_shop import seed_sample_shop


def test_seed_small_execution_and_integrity():
    """Test seed_sample_shop with --small flag and verify row counts and 100% total_amount accuracy."""
    # Run seed in small mode with reset
    seed_sample_shop(
        database_url=settings.shop_admin_database_url,
        seed=123,
        small=True,
        reset=True,
    )

    raw_url = settings.shop_admin_database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw_url) as conn, conn.cursor() as cur:
        # Check row counts
        cur.execute("SELECT count(*) FROM users;")
        users_count = cur.fetchone()[0]
        assert users_count == 1000

        cur.execute("SELECT count(*) FROM products;")
        products_count = cur.fetchone()[0]
        assert products_count == 200

        cur.execute("SELECT count(*) FROM orders;")
        orders_count = cur.fetchone()[0]
        assert orders_count == 5000

        cur.execute("SELECT count(*) FROM order_items;")
        items_count = cur.fetchone()[0]
        assert items_count >= 10000

        # Verify that total_amount equals sum of line items for 100% of orders
        cur.execute("""
            SELECT count(*)
            FROM orders o
            LEFT JOIN (
                SELECT order_id, SUM(quantity * unit_price) AS items_sum
                FROM order_items
                GROUP BY order_id
            ) i ON o.id = i.order_id
            WHERE ABS(o.total_amount - COALESCE(i.items_sum, 0)) > 0.001;
        """)
        mismatches = cur.fetchone()[0]
        assert mismatches == 0, (
            f"Expected 0 mismatches between order total_amount and items sum, got {mismatches}"
        )
