import psycopg
import pytest
from psycopg import errors

from app.core.config import settings


def get_readonly_conn():
    raw_url = settings.shop_database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(raw_url, autocommit=False)


def test_readonly_user_can_select():
    """Verify readonly_user has SELECT permission on all sample_shop tables."""
    with get_readonly_conn() as conn, conn.cursor() as cur:
        for table in ("users", "products", "orders", "order_items"):
            cur.execute(f"SELECT count(*) FROM {table};")
            result = cur.fetchone()
            assert result is not None
            assert isinstance(result[0], int)


def test_readonly_user_cannot_insert():
    """Verify readonly_user is denied INSERT permission."""
    with get_readonly_conn() as conn:
        with conn.cursor() as cur, pytest.raises(errors.InsufficientPrivilege):
            cur.execute("INSERT INTO users (name, email, country) VALUES ('Hacker', 'hacker@bad.com', 'US');")
        conn.rollback()


def test_readonly_user_cannot_update():
    """Verify readonly_user is denied UPDATE permission."""
    with get_readonly_conn() as conn:
        with conn.cursor() as cur, pytest.raises(errors.InsufficientPrivilege):
            cur.execute("UPDATE products SET price = 0.01 WHERE id = 1;")
        conn.rollback()


def test_readonly_user_cannot_delete():
    """Verify readonly_user is denied DELETE permission."""
    with get_readonly_conn() as conn:
        with conn.cursor() as cur, pytest.raises(errors.InsufficientPrivilege):
            cur.execute("DELETE FROM orders WHERE id = 1;")
        conn.rollback()


def test_readonly_user_cannot_drop_table():
    """Verify readonly_user is denied DDL DROP TABLE permission."""
    with get_readonly_conn() as conn:
        with conn.cursor() as cur, pytest.raises(errors.InsufficientPrivilege):
            cur.execute("DROP TABLE order_items;")
        conn.rollback()
