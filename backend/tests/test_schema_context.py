"""Unit and caching tests for compact schema context generator."""

from unittest.mock import patch

import pytest

from app.services.schema_context import (
    format_schema_description,
    get_schema_context,
    invalidate_schema_context_cache,
)


@pytest.mark.asyncio
class TestSchemaContext:
    """Test suite for schema context formatting and in-memory TTL caching."""

    async def test_schema_context_contains_only_allowed_tables(self):
        invalidate_schema_context_cache()
        context = await get_schema_context()

        # Must include all 4 business tables
        assert "TABLE users:" in context
        assert "TABLE products:" in context
        assert "TABLE orders:" in context
        assert "TABLE order_items:" in context

        # Must NOT include alembic_version or pg_catalog
        assert "alembic_version" not in context
        assert "pg_catalog" not in context
        assert "information_schema" not in context

        # Must include specific key constraints and enums
        assert "PRIMARY KEY" in context
        assert "FOREIGN KEY" in context
        assert "pending" in context
        assert "delivered" in context

    async def test_schema_context_caching_does_not_hit_database_on_second_call(self):
        invalidate_schema_context_cache()
        # First call hits database and formats description
        first_text = await get_schema_context()
        assert first_text is not None

        # Second call within TTL should return cached text without re-formatting
        with patch("app.services.schema_context.format_schema_description") as mock_format:
            second_text = await get_schema_context()
            assert second_text == first_text
            mock_format.assert_not_called()

    async def test_invalidate_cache_forces_database_refresh(self):
        # Populate cache
        await get_schema_context()

        # Invalidate
        invalidate_schema_context_cache()

        # Next call must hit database and re-format
        with patch(
            "app.services.schema_context.format_schema_description", wraps=format_schema_description
        ) as mock_format:
            await get_schema_context()
            mock_format.assert_called_once()

    async def test_format_schema_description_structure(self):
        sample_meta = {
            "users": {
                "columns": [
                    {"name": "id", "type": "BIGINT", "nullable": False},
                    {"name": "email", "type": "VARCHAR(255)", "nullable": False},
                ],
                "primary_key": ["id"],
                "foreign_keys": [],
            },
            "ignored_table": {
                "columns": [{"name": "secret", "type": "TEXT", "nullable": True}],
                "primary_key": [],
                "foreign_keys": [],
            },
        }
        res = format_schema_description(sample_meta)
        assert "TABLE users:" in res
        assert "ignored_table" not in res
        assert "PRIMARY KEY" in res
