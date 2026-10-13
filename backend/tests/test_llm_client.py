"""Unit tests for LLM clients, retry backoff, and exception mappings."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.llm.base import (
    LLMInvalidResponse,
    LLMRateLimit,
    LLMTimeout,
    LLMUnavailable,
)
from app.services.llm.fake import FakeLLM
from app.services.llm.openai import OpenAILLMClient


@pytest.mark.asyncio
class TestFakeLLM:
    """Test suite for FakeLLM test double."""

    async def test_fake_llm_returns_scripted_responses_in_order(self):
        fake = FakeLLM(
            responses=[
                {"sql": "SELECT 1", "explanation": "first"},
                {"sql": "SELECT 2", "explanation": "second"},
            ]
        )
        res1 = await fake.complete_json("sys", "user1")
        assert res1["sql"] == "SELECT 1"

        res2 = await fake.complete_json("sys", "user2")
        assert res2["sql"] == "SELECT 2"

        # Third call falls back to default
        res3 = await fake.complete_json("sys", "user3")
        assert "sql" in res3
        assert len(fake.calls) == 3

    async def test_fake_llm_raises_scripted_exceptions(self):
        fake = FakeLLM(responses=[LLMTimeout("Scripted timeout")])
        with pytest.raises(LLMTimeout) as exc:
            await fake.complete_json("sys", "user")
        assert "Scripted timeout" in str(exc.value)


@pytest.mark.asyncio
class TestOpenAILLMClient:
    """Test suite for OpenAILLMClient HTTP interactions and retries."""

    async def test_missing_api_key_raises_llm_unavailable(self):
        client = OpenAILLMClient(api_key="")
        with pytest.raises(LLMUnavailable) as exc:
            await client.complete_json("sys", "user")
        assert "API key is not configured" in str(exc.value)

    async def test_successful_json_completion(self):
        client = OpenAILLMClient(api_key="sk-test-key")
        mock_response = httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"sql": "SELECT * FROM users", "explanation": "test"}'
                        }
                    }
                ]
            },
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            res = await client.complete_json("sys", "user")
            assert res["sql"] == "SELECT * FROM users"
            assert res["explanation"] == "test"
            mock_post.assert_called_once()

    async def test_transient_error_retries_with_exponential_backoff(self):
        client = OpenAILLMClient(api_key="sk-test-key")
        # 1st attempt: 429, 2nd attempt: 200
        resp_429 = httpx.Response(status_code=429, text="Rate limited")
        resp_200 = httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": '{"sql": "SELECT 1"}'}}]},
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.side_effect = [resp_429, resp_200]
            res = await client.complete_json("sys", "user")
            assert res["sql"] == "SELECT 1"
            assert mock_post.call_count == 2
            mock_sleep.assert_called_once_with(0.5)

    async def test_exhausted_retries_raises_llm_rate_limit(self):
        client = OpenAILLMClient(api_key="sk-test-key")
        resp_429 = httpx.Response(status_code=429, text="Rate limited")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, patch("asyncio.sleep", new_callable=AsyncMock):
            mock_post.side_effect = [resp_429, resp_429, resp_429]
            with pytest.raises(LLMRateLimit):
                await client.complete_json("sys", "user")
            assert mock_post.call_count == 3

    async def test_permanent_400_error_is_never_retried(self):
        client = OpenAILLMClient(api_key="sk-test-key")
        resp_400 = httpx.Response(status_code=400, text="Bad Request: invalid_model")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = resp_400
            with pytest.raises(LLMUnavailable) as exc:
                await client.complete_json("sys", "user")
            assert mock_post.call_count == 1
            assert "HTTP 400" in str(exc.value)

    async def test_timeout_raises_llm_timeout(self):
        client = OpenAILLMClient(api_key="sk-test-key")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Read timed out")
            with pytest.raises(LLMTimeout):
                await client.complete_json("sys", "user")

    async def test_malformed_json_raises_llm_invalid_response(self):
        client = OpenAILLMClient(api_key="sk-test-key")
        mock_response = httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": "This is not valid JSON at all"}}]},
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            with pytest.raises(LLMInvalidResponse):
                await client.complete_json("sys", "user")

