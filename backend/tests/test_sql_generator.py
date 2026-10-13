"""Unit tests for SQL generator prompts, safety delimiters, and JSON parsing/retry logic."""

import pytest

from app.services.llm.base import LLMInvalidResponse
from app.services.llm.fake import FakeLLM
from app.services.sql_generator import (
    GeneratedSQLResponse,
    build_repair_user_prompt,
    build_system_prompt,
    build_user_prompt,
    generate_sql_response,
)


@pytest.mark.asyncio
class TestSqlGenerator:
    """Test suite for prompt engineering, security boundaries, and response parsing."""

    async def test_build_system_prompt_includes_schema_and_rules(self):
        prompt = build_system_prompt("MOCK_SCHEMA_CONTEXT")
        assert "MOCK_SCHEMA_CONTEXT" in prompt
        assert "PostgreSQL 16" in prompt
        assert "CRITICAL RULES" in prompt
        assert "<user_question>" in prompt
        assert "response_format" not in prompt  # rules specify json contract

    async def test_build_user_prompt_wraps_in_delimiters_and_truncates(self):
        short_prompt = build_user_prompt("Who are the top customers?")
        assert "<user_question>\nWho are the top customers?\n</user_question>" in short_prompt

        long_question = "A" * 1500
        truncated_prompt = build_user_prompt(long_question)
        assert len(long_question) > 1000
        assert "<user_question>\n" + ("A" * 1000) + "\n</user_question>" in truncated_prompt

    async def test_build_repair_prompt_contains_previous_sql_and_error(self):
        repair_prompt = build_repair_user_prompt(
            question="Show orders",
            previous_sql="SELECT * FROM secret",
            error_message="Table 'secret' is not permitted",
        )
        assert "SELECT * FROM secret" in repair_prompt
        assert "Table 'secret' is not permitted" in repair_prompt
        assert "<user_question>\nShow orders\n</user_question>" in repair_prompt

    async def test_generate_sql_response_success_on_first_try(self):
        fake = FakeLLM(
            responses=[
                {
                    "sql": "SELECT id, name FROM users LIMIT 5",
                    "explanation": "Top 5 users",
                    "assumptions": ["Ordered by id"],
                    "needs_clarification": False,
                    "clarification_question": None,
                }
            ]
        )
        resp = await generate_sql_response(
            llm=fake,
            system_prompt="sys",
            user_prompt="user",
        )
        assert isinstance(resp, GeneratedSQLResponse)
        assert resp.sql == "SELECT id, name FROM users LIMIT 5"
        assert resp.explanation == "Top 5 users"
        assert resp.assumptions == ["Ordered by id"]
        assert resp.needs_clarification is False

    async def test_generate_sql_response_retries_on_schema_violation_and_recovers(self):
        # 1st attempt: missing required 'sql' field
        # 2nd attempt: corrected payload
        fake = FakeLLM(
            responses=[
                {"explanation": "Missing sql key"},
                {
                    "sql": "SELECT count(*) FROM products",
                    "explanation": "Recovered count",
                    "assumptions": [],
                    "needs_clarification": False,
                    "clarification_question": None,
                },
            ]
        )
        resp = await generate_sql_response(
            llm=fake,
            system_prompt="sys",
            user_prompt="user",
        )
        assert resp.sql == "SELECT count(*) FROM products"
        assert len(fake.calls) == 2
        # Verify the retry prompt included the error notice
        assert "CRITICAL: Your previous response failed schema validation" in fake.calls[1]["user_prompt"]

    async def test_generate_sql_response_fails_after_retry(self):
        # Both attempts invalid
        fake = FakeLLM(
            responses=[
                {"invalid": 1},
                {"still_invalid": 2},
            ]
        )
        with pytest.raises(LLMInvalidResponse) as exc:
            await generate_sql_response(
                llm=fake,
                system_prompt="sys",
                user_prompt="user",
            )
        assert "Failed to obtain valid JSON from LLM after retry" in str(exc.value)
