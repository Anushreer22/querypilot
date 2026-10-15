"""SQL-level injection attack test suite verifying AST security, execution bounds, and audit history."""

import httpx
import pytest
from sqlalchemy import select

from app.db.models import QueryHistory
from app.db.session import AppAsyncSessionLocal


async def get_latest_audit_entry() -> QueryHistory | None:
    """Retrieve the most recent query audit entry from querypilot_app."""
    async with AppAsyncSessionLocal() as session:
        result = await session.execute(
            select(QueryHistory).order_by(QueryHistory.id.desc()).limit(1)
        )
        return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_stacked_statements_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT id FROM users; DROP TABLE users;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422
    assert (
        "multiple" in resp.json()["detail"].lower() or "rejected" in resp.json()["detail"].lower()
    )

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"
    assert entry.source == "sec_test"


@pytest.mark.asyncio
async def test_comment_tricks_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT 1 -- line comment\n; DROP TABLE orders;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_nested_comments_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT /* outer /* inner */ */ id FROM users; DELETE FROM orders;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_case_variation_mutation_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "dRoP tAbLe products;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_dollar_quoted_string_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT $$evil$$; DROP TABLE users;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_schema_qualified_dangerous_function_rejected(
    async_client: httpx.AsyncClient,
) -> None:
    sql = "SELECT pg_catalog.pg_sleep(5);"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422
    assert "function" in resp.json()["detail"].lower()

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_table_valued_function_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT * FROM generate_series(1, 1000);"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_select_into_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT * INTO hacker_users FROM users;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_locking_clause_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT * FROM orders FOR UPDATE;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_data_modifying_cte_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "WITH deleted AS (DELETE FROM orders RETURNING *) SELECT * FROM deleted;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_system_catalogs_rejected(async_client: httpx.AsyncClient) -> None:
    catalogs = [
        "SELECT * FROM pg_class;",
        "SELECT * FROM pg_authid;",
        "SELECT * FROM pg_shadow;",
        "SELECT * FROM information_schema.tables;",
    ]
    for sql in catalogs:
        resp = await async_client.post(
            "/api/query/execute", json={"sql": sql, "source": "sec_test"}
        )
        assert resp.status_code == 422
        entry = await get_latest_audit_entry()
        assert entry is not None
        assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_other_schemas_rejected(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT * FROM querypilot_app.query_history;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 422

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "rejected"


@pytest.mark.asyncio
async def test_huge_limit_clamped(async_client: httpx.AsyncClient) -> None:
    sql = "SELECT id, name FROM users LIMIT 10000000 OFFSET 0;"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["limit_injected"] is True
    assert "LIMIT 1000" in data["sanitized_sql"]

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "success"


@pytest.mark.asyncio
async def test_statement_timeout_cancels_cartesian_query(async_client: httpx.AsyncClient) -> None:
    # Heavy Cartesian product cross join forced to exceed timeout
    sql = "SELECT count(*) FROM orders o1 CROSS JOIN orders o2 CROSS JOIN orders o3;"
    # Execute with short timeout (500ms) to trigger 504 cancellation quickly
    resp = await async_client.post(
        "/api/query/execute",
        json={"sql": sql, "source": "sec_test", "timeout_ms": 500},
    )
    assert resp.status_code == 504

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "timeout"


@pytest.mark.asyncio
async def test_very_long_sql_handled_safely(async_client: httpx.AsyncClient) -> None:
    # 1. Test query within max_length (e.g. 800 items, ~4500 chars) is processed and audited
    ids_str = ", ".join(str(i) for i in range(1, 801))
    sql = f"SELECT id, name FROM products WHERE id IN ({ids_str});"
    resp = await async_client.post("/api/query/execute", json={"sql": sql, "source": "sec_test"})
    assert resp.status_code == 200

    entry = await get_latest_audit_entry()
    assert entry is not None
    assert entry.status == "success"

    # 2. Test query exceeding 10,000 characters is safely rejected with 422
    huge_sql = (
        "SELECT id FROM products WHERE id IN (" + ", ".join(str(i) for i in range(1, 3000)) + ");"
    )
    assert len(huge_sql) > 10000
    resp_huge = await async_client.post(
        "/api/query/execute", json={"sql": huge_sql, "source": "sec_test"}
    )
    assert resp_huge.status_code == 422
    assert "at most 10000 characters" in resp_huge.text or "string_too_long" in resp_huge.text
