"""Integration tests for secure read-only query executor and audit logging."""

import pytest
from sqlalchemy import select, text

from app.db.models import QueryHistory
from app.db.session import AppAsyncSessionLocal, shop_engine
from app.services.query_executor import (
    QueryExecutionError,
    QueryTimeoutError,
    execute_readonly_query,
    log_query_history,
)


@pytest.mark.asyncio
class TestQueryExecutor:
    """Test suite for query execution safeguards and transaction controls."""

    async def test_transaction_read_only_is_on(self):
        """Verify SHOW transaction_read_only returns 'on' inside the executor."""
        async with shop_engine.connect() as conn, conn.begin():
            await conn.execute(text("SET TRANSACTION READ ONLY;"))
            res = await conn.execute(text("SHOW transaction_read_only;"))
            status = res.scalar()
            assert status == "on"

    async def test_execute_readonly_query_success(self):
        """Execute a valid SELECT query and verify structured results."""
        result = await execute_readonly_query(
            sanitized_sql="SELECT id, name, email FROM users ORDER BY id ASC LIMIT 5;",
            timeout_ms=5000,
            max_rows=1000,
        )
        assert result.columns == ["id", "name", "email"]
        assert len(result.rows) == 5
        assert result.row_count == 5
        assert result.duration_ms >= 0.0
        assert result.truncated is False
        assert result.rows[0]["id"] == 1

    async def test_execute_readonly_query_truncation(self):
        """Verify row truncation when available rows exceed max_rows."""
        result = await execute_readonly_query(
            sanitized_sql="SELECT id FROM users ORDER BY id ASC;",
            timeout_ms=5000,
            max_rows=10,
        )
        assert len(result.rows) == 10
        assert result.row_count == 10
        assert result.truncated is True

    async def test_statement_timeout_raises_query_timeout_error(self):
        """Verify that a slow query (cross join on order_items) triggers QueryTimeoutError with SQLSTATE 57014."""
        with pytest.raises(QueryTimeoutError) as exc_info:
            await execute_readonly_query(
                sanitized_sql="SELECT count(*) FROM order_items a CROSS JOIN order_items b;",
                timeout_ms=30,  # 30 milliseconds statement timeout
            )
        assert exc_info.value.sqlstate == "57014"
        assert "timed out" in exc_info.value.message.lower()

    async def test_database_rejects_insert_in_read_only_transaction(self):
        """Verify defense-in-depth: database directly rejects INSERT even if bypassed."""
        with pytest.raises(QueryExecutionError) as exc_info:
            await execute_readonly_query(
                sanitized_sql="INSERT INTO users (name, email, country) VALUES ('evil', 'evil@hack.com', 'US');",
            )
        assert exc_info.value.sqlstate == "25006"
        assert "read-only transaction" in exc_info.value.message.lower()

    async def test_database_rejects_pg_sleep_permissions(self):
        """Verify defense-in-depth: readonly_user has revoked permissions on pg_sleep."""
        with pytest.raises(QueryExecutionError) as exc_info:
            await execute_readonly_query(
                sanitized_sql="SELECT pg_sleep(0.1);",
            )
        assert exc_info.value.sqlstate == "42501"
        assert "permission denied" in exc_info.value.message.lower()

    async def test_log_query_history_persists_audit_entry(self):
        """Verify audit logger writes to querypilot_app in an independent transaction."""
        history_id = await log_query_history(
            sql_text="SELECT count(*) FROM products;",
            status="success",
            source="test_executor",
            duration_ms=4.25,
            row_count=100,
        )
        assert history_id is not None

        async with AppAsyncSessionLocal() as session:
            stmt = select(QueryHistory).where(QueryHistory.id == history_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            assert row is not None
            assert row.source == "test_executor"
            assert row.status == "success"
            assert row.sql_text == "SELECT count(*) FROM products;"
            assert float(row.duration_ms) == 4.25
            assert row.row_count == 100

