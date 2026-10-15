"""Integration tests for Query API endpoints (/api/schema, /api/query/execute, /api/query/history)."""

import httpx
import pytest


@pytest.mark.asyncio
class TestSchemaApi:
    """Tests for GET /api/schema."""

    async def test_get_schema_metadata(self, async_client: httpx.AsyncClient):
        response = await async_client.get("/api/schema")
        assert response.status_code == 200
        data = response.json()

        assert "tables" in data
        tables = data["tables"]
        table_names = {t["name"] for t in tables}

        # Must include all 4 business tables
        expected_tables = {"users", "products", "orders", "order_items"}
        assert expected_tables.issubset(table_names)
        assert "alembic_version" not in table_names

        # Verify orders table metadata
        orders_table = next(t for t in tables if t["name"] == "orders")
        assert "id" in orders_table["primary_key"]
        order_col_names = {c["name"] for c in orders_table["columns"]}
        assert {"id", "user_id", "status", "total_amount", "created_at"}.issubset(order_col_names)

        # Verify foreign keys on orders
        assert len(orders_table["foreign_keys"]) == 1
        fk = orders_table["foreign_keys"][0]
        assert fk["referred_table"] == "users"
        assert fk["constrained_columns"] == ["user_id"]
        assert fk["referred_columns"] == ["id"]


@pytest.mark.asyncio
class TestQueryExecuteApi:
    """Tests for POST /api/query/execute."""

    async def test_execute_valid_query(self, async_client: httpx.AsyncClient):
        payload = {
            "sql": "SELECT id, name, email FROM users ORDER BY id ASC LIMIT 3",
            "source": "api_test",
        }
        response = await async_client.post("/api/query/execute", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["columns"] == ["id", "name", "email"]
        assert len(data["rows"]) == 3
        assert data["row_count"] == 3
        assert data["limit_injected"] is False
        assert data["truncated"] is False
        assert "users" in data["sanitized_sql"].lower()

    async def test_execute_query_with_limit_injection(self, async_client: httpx.AsyncClient):
        payload = {
            "sql": "SELECT id FROM users",
            "source": "api_test",
        }
        response = await async_client.post("/api/query/execute", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["limit_injected"] is True
        assert "limit 1000" in data["sanitized_sql"].lower()

    async def test_execute_query_validation_rejection(self, async_client: httpx.AsyncClient):
        payload = {
            "sql": "DROP TABLE users",
            "source": "api_test",
        }
        response = await async_client.post("/api/query/execute", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "only select statements are allowed" in data["detail"].lower()

    async def test_execute_query_dangerous_func_rejected(self, async_client: httpx.AsyncClient):
        payload = {
            "sql": "SELECT pg_sleep(1)",
            "source": "api_test",
        }
        response = await async_client.post("/api/query/execute", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "pg_sleep" in data["detail"].lower()

    async def test_execute_query_disallowed_table_rejected(self, async_client: httpx.AsyncClient):
        payload = {
            "sql": "SELECT * FROM secret_credentials",
            "source": "api_test",
        }
        response = await async_client.post("/api/query/execute", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert "secret_credentials" in data["detail"].lower()

    async def test_execute_query_database_error_returns_400(self, async_client: httpx.AsyncClient):
        payload = {
            "sql": "SELECT non_existent_column FROM users",
            "source": "api_test",
        }
        response = await async_client.post("/api/query/execute", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "non_existent_column" in data["detail"].lower()

    async def test_execute_query_timeout_returns_504(self, async_client: httpx.AsyncClient):
        payload = {
            "sql": "SELECT count(*) FROM order_items a CROSS JOIN order_items b",
            "source": "api_test",
            "timeout_ms": 30,  # 30ms timeout
        }
        response = await async_client.post("/api/query/execute", json=payload)
        assert response.status_code == 504
        data = response.json()
        assert "detail" in data
        assert "timed out" in data["detail"].lower()


@pytest.mark.asyncio
class TestQueryHistoryApi:
    """Tests for GET /api/query/history."""

    async def test_query_history_contains_logged_attempts(self, async_client: httpx.AsyncClient):
        # 1. Execute a valid query to ensure history has entries
        await async_client.post(
            "/api/query/execute",
            json={"sql": "SELECT count(*) FROM products", "source": "history_test"},
        )

        # 2. Query history
        response = await async_client.get("/api/query/history?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert data["total"] > 0
        assert len(data["items"]) > 0

        first_item = data["items"][0]
        assert "id" in first_item
        assert "source" in first_item
        assert "sql_text" in first_item
        assert "status" in first_item
        assert first_item["status"] in ("success", "rejected", "error", "timeout")
        assert "created_at" in first_item

    async def test_query_history_pagination(self, async_client: httpx.AsyncClient):
        response1 = await async_client.get("/api/query/history?limit=2&offset=0")
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["items"]) <= 2

        response2 = await async_client.get("/api/query/history?limit=2&offset=2")
        assert response2.status_code == 200
        data2 = response2.json()

        # If more than 2 items exist, offset pages should have different IDs
        if data1["total"] > 2 and len(data2["items"]) > 0:
            ids_page1 = {item["id"] for item in data1["items"]}
            ids_page2 = {item["id"] for item in data2["items"]}
            assert ids_page1.isdisjoint(ids_page2)
