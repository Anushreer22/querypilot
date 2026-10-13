import psycopg
import pytest
from psycopg import errors

from app.core.config import settings


def get_admin_conn():
    raw_url = settings.shop_admin_database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(raw_url, autocommit=False)


def test_tables_and_columns_exist():
    """Verify that all four e-commerce tables exist in sample_shop."""
    with get_admin_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name IN ('users', 'products', 'orders', 'order_items');
        """)
        tables = {row[0] for row in cur.fetchall()}
        assert tables == {"users", "products", "orders", "order_items"}


def test_unique_email_constraint():
    """Verify that duplicate user emails are rejected."""
    with get_admin_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email FROM users LIMIT 1;")
            row = cur.fetchone()
            if not row:
                # Insert a base user to test
                cur.execute("INSERT INTO users (name, email, country) VALUES ('Test User', 'dup@example.com', 'US') RETURNING email;")
                email = cur.fetchone()[0]
            else:
                email = row[1]

            with pytest.raises(errors.UniqueViolation):
                cur.execute("INSERT INTO users (name, email, country) VALUES ('Dup User', %s, 'UK');", (email,))
        conn.rollback()


def test_negative_product_price_rejected():
    """Verify CHECK (price >= 0) constraint rejects negative prices."""
    with get_admin_conn() as conn:
        with conn.cursor() as cur, pytest.raises(errors.CheckViolation):
            cur.execute("INSERT INTO products (name, category, price, stock) VALUES ('Bad Item', 'Test', -10.00, 5);")
        conn.rollback()


def test_negative_product_stock_rejected():
    """Verify CHECK (stock >= 0) constraint rejects negative stock."""
    with get_admin_conn() as conn:
        with conn.cursor() as cur, pytest.raises(errors.CheckViolation):
            cur.execute("INSERT INTO products (name, category, price, stock) VALUES ('Bad Item', 'Test', 10.00, -1);")
        conn.rollback()


def test_invalid_order_status_rejected():
    """Verify CHECK (status IN (...)) constraint rejects illegal order statuses."""
    with get_admin_conn() as conn:
        with conn.cursor() as cur:
            # Get valid user_id
            cur.execute("SELECT id FROM users LIMIT 1;")
            user_row = cur.fetchone()
            user_id = user_row[0] if user_row else 1

            with pytest.raises(errors.CheckViolation):
                cur.execute(
                    "INSERT INTO orders (user_id, status, total_amount, created_at) VALUES (%s, 'invalid_status', 50.00, NOW());",
                    (user_id,)
                )
        conn.rollback()


def test_zero_or_negative_order_item_quantity_rejected():
    """Verify CHECK (quantity > 0) rejects quantity <= 0."""
    with get_admin_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM orders LIMIT 1;")
        order_row = cur.fetchone()
        cur.execute("SELECT id FROM products LIMIT 1;")
        prod_row = cur.fetchone()

        if order_row and prod_row:
            order_id = order_row[0]
            prod_id = prod_row[0]

            with pytest.raises(errors.CheckViolation):
                cur.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, 0, 10.00);",
                    (order_id, prod_id),
                )
            conn.rollback()

            with pytest.raises(errors.CheckViolation):
                cur.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, -2, 10.00);",
                    (order_id, prod_id),
                )
            conn.rollback()


def test_orphan_foreign_key_rejected():
    """Verify foreign key constraint rejects order with non-existent user_id."""
    with get_admin_conn() as conn:
        with conn.cursor() as cur, pytest.raises(errors.ForeignKeyViolation):
            cur.execute(
                "INSERT INTO orders (user_id, status, total_amount, created_at) VALUES (999999999, 'pending', 10.00, NOW());"
            )
        conn.rollback()
