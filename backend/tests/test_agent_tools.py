"""Unit tests for agent tools and ToolRegistry."""

import pytest
from sqlalchemy import text

from app.agent.tools.base import ToolRegistry
from app.agent.tools.execute_query import execute_readonly_query_tool
from app.agent.tools.explain_query import explain_query_tool
from app.agent.tools.inspect_schema import inspect_schema_tool
from app.agent.tools.query_history import get_query_history_tool
from app.agent.tools.validate_sql import validate_sql_tool
from app.core.config import settings
from app.db.session import shop_engine


@pytest.mark.asyncio
async def test_inspect_schema_all_tables():
    """Test inspect_schema returns all 4 allowed business tables."""
    result = await inspect_schema_tool.handler(
        inspect_schema_tool.args_schema(table=None)
    )
    assert result["ok"] is True
    schema_text = result["schema"]
    assert "users" in schema_text
    assert "products" in schema_text
    assert "orders" in schema_text
    assert "order_items" in schema_text
    assert "pg_catalog" not in schema_text


@pytest.mark.asyncio
async def test_inspect_schema_single_valid_table():
    """Test inspect_schema for a single allowed table."""
    result = await inspect_schema_tool.handler(
        inspect_schema_tool.args_schema(table="users")
    )
    assert result["ok"] is True
    assert result["table"] == "users"
    assert "TABLE users:" in result["schema"]
    assert "TABLE products:" not in result["schema"]


@pytest.mark.asyncio
async def test_inspect_schema_disallowed_table():
    """Test inspect_schema rejects system or disallowed tables."""
    result = await inspect_schema_tool.handler(
        inspect_schema_tool.args_schema(table="pg_shadow")
    )
    assert result["ok"] is False
    assert "not permitted" in result["error"] or "unknown" in result["error"]


@pytest.mark.asyncio
async def test_validate_sql_valid_query():
    """Test validate_sql validates safe queries without executing them."""
    result = await validate_sql_tool.handler(
        validate_sql_tool.args_schema(sql="SELECT id, name FROM users WHERE id = 1")
    )
    assert result["ok"] is True
    assert "sanitized_sql" in result
    assert "LIMIT" in result["sanitized_sql"]


@pytest.mark.asyncio
async def test_validate_sql_forbidden_mutation():
    """Test validate_sql rejects data-modifying statements."""
    result = await validate_sql_tool.handler(
        validate_sql_tool.args_schema(sql="DROP TABLE users;")
    )
    assert result["ok"] is False
    assert result["reason"] is not None


@pytest.mark.asyncio
async def test_execute_readonly_query_success():
    """Test execute_readonly_query executes valid query and caps row preview."""
    result = await execute_readonly_query_tool.handler(
        execute_readonly_query_tool.args_schema(
            sql="SELECT id, name, email FROM users ORDER BY id LIMIT 5"
        )
    )
    assert result["ok"] is True
    assert "columns" in result
    assert "id" in result["columns"]
    assert len(result["rows"]) <= 20
    assert result["row_count"] >= 1
    assert result["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_execute_readonly_query_rejects_and_prevents_write():
    """Test execute_readonly_query refuses INSERT and proves zero writes occur."""
    async with shop_engine.connect() as conn:
        before_count = (await conn.execute(text("SELECT count(*) FROM users"))).scalar()

    result = await execute_readonly_query_tool.handler(
        execute_readonly_query_tool.args_schema(
            sql="INSERT INTO users (name, email, country) VALUES ('Hacker', 'hack@evil.com', 'US')"
        )
    )
    assert result["ok"] is False
    assert "rejected" in result["error"].lower()

    async with shop_engine.connect() as conn:
        after_count = (await conn.execute(text("SELECT count(*) FROM users"))).scalar()

    assert before_count == after_count


@pytest.mark.asyncio
async def test_execute_readonly_query_row_preview_toggle(monkeypatch):
    """Test that setting AGENT_SEND_ROW_PREVIEW=False omits rows preview."""
    monkeypatch.setattr(settings, "agent_send_row_preview", False)
    result = await execute_readonly_query_tool.handler(
        execute_readonly_query_tool.args_schema(
            sql="SELECT id, name FROM users LIMIT 3"
        )
    )
    assert result["ok"] is True
    assert result["rows"] == []
    assert result["row_count"] >= 1


@pytest.mark.asyncio
async def test_explain_query_plain_json():
    """Test explain_query returns plan cost, row estimates, and Seq Scan check."""
    result = await explain_query_tool.handler(
        explain_query_tool.args_schema(sql="SELECT * FROM users WHERE id = 10")
    )
    assert result["ok"] is True
    assert "node_type" in result
    assert "total_cost" in result
    assert "plan_rows" in result
    assert "has_seq_scan" in result
    assert isinstance(result["has_seq_scan"], bool)


@pytest.mark.asyncio
async def test_explain_query_rejects_forbidden_statements():
    """Test explain_query rejects mutations before planning."""
    result = await explain_query_tool.handler(
        explain_query_tool.args_schema(sql="DELETE FROM users WHERE id = 1")
    )
    assert result["ok"] is False
    assert "rejected" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_query_history_tool():
    """Test get_query_history returns recent history with safe fields."""
    result = await get_query_history_tool.handler(
        get_query_history_tool.args_schema(limit=5)
    )
    assert result["ok"] is True
    assert "entries" in result
    assert isinstance(result["entries"], list)
    if result["entries"]:
        first = result["entries"][0]
        assert "sql" in first
        assert "status" in first
        assert "created_at" in first


@pytest.mark.asyncio
async def test_tool_registry_unknown_tool_and_invalid_args():
    """Test ToolRegistry handles unknown tool names and invalid arguments without crashing."""
    registry = ToolRegistry()
    registry.register(validate_sql_tool)

    # Unknown tool
    unknown_res = await registry.execute("hack_database", {"arg": "val"})
    assert unknown_res["ok"] is False
    assert "Unknown tool" in unknown_res["error"]

    # Invalid arguments (missing required 'sql')
    invalid_args_res = await registry.execute("validate_sql", {})
    assert invalid_args_res["ok"] is False
    assert "Invalid arguments" in invalid_args_res["error"]


@pytest.mark.asyncio
async def test_analyze_query_plan_tool_valid():
    """Test analyze_query_plan returns plan findings and index suggestions without executing DDL."""
    from app.agent.tools.analyze_query_plan import analyze_query_plan_tool

    result = await analyze_query_plan_tool.handler(
        analyze_query_plan_tool.args_schema(
            sql="SELECT id, total_amount FROM orders WHERE created_at >= '2026-01-01' LIMIT 20;"
        )
    )
    assert result["ok"] is True
    assert "findings" in result
    assert "suggestions" in result
    assert "total_cost" in result
    assert "summary" in result


@pytest.mark.asyncio
async def test_analyze_query_plan_tool_rejected():
    """Test analyze_query_plan returns structured error on invalid/rejected SQL."""
    from app.agent.tools.analyze_query_plan import analyze_query_plan_tool

    result = await analyze_query_plan_tool.handler(
        analyze_query_plan_tool.args_schema(
            sql="DROP TABLE users;"
        )
    )
    assert result["ok"] is False
    assert "error" in result

