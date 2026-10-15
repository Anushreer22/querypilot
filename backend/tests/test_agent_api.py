"""Integration tests for POST /api/agent/ask and GET /api/agent/runs endpoints."""

import os

import httpx
import pytest

from app.api.agent import agent_rate_limiter
from app.services.llm.base import (
    LLMUnavailable,
    ToolCall,
    ToolCompletionResult,
)
from app.services.llm.factory import set_llm_client
from app.services.llm.fake import FakeLLM


@pytest.fixture(autouse=True)
def setup_agent_fixtures():
    """Reset rate limiter and clear LLM overrides before and after each test."""
    agent_rate_limiter.reset()
    yield
    set_llm_client(None)
    agent_rate_limiter.reset()


@pytest.mark.asyncio
async def test_agent_ask_completed_200(async_client: httpx.AsyncClient):
    """Test POST /api/agent/ask returns 200 with completed status and results."""
    fake_llm = FakeLLM()
    # Step 1: execute query
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(
                    id="tc_1",
                    name="execute_readonly_query",
                    arguments={"sql": "SELECT id, name FROM users ORDER BY id LIMIT 2"},
                )
            ]
        )
    )
    # Step 2: final answer
    fake_llm.enqueue_tool_response(ToolCompletionResult(content="Found 2 users: Alice and Bob."))
    set_llm_client(fake_llm)

    response = await async_client.post(
        "/api/agent/ask",
        json={"question": "List the first two users."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "Alice and Bob" in data["final_answer"]
    assert data["sql"] is not None
    assert data["results"] is not None
    assert data["results"]["row_count"] == 2
    assert len(data["steps"]) == 1
    assert data["steps"][0]["tool"] == "execute_readonly_query"
    assert data["run_id"] is not None


@pytest.mark.asyncio
async def test_agent_ask_clarification_200(async_client: httpx.AsyncClient):
    """Test POST /api/agent/ask returns 200 for clarification without query execution."""
    fake_llm = FakeLLM()
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(content="Could you clarify if you mean active users or all users?")
    )
    set_llm_client(fake_llm)

    response = await async_client.post(
        "/api/agent/ask",
        json={"question": "Get users."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "clarification"
    assert "could you clarify" in data["final_answer"].lower()
    assert data["sql"] is None
    assert data["results"] is None


@pytest.mark.asyncio
async def test_agent_ask_step_limit_422(async_client: httpx.AsyncClient):
    """Test POST /api/agent/ask returns 422 when step limit is hit without conclusion."""
    fake_llm = FakeLLM()
    # Enqueue 10 inspect_schema responses (default max_steps is 6)
    for i in range(10):
        fake_llm.enqueue_tool_response(
            ToolCompletionResult(
                tool_calls=[
                    ToolCall(id=f"tc_{i}", name="inspect_schema", arguments={"table": "users"})
                ]
            )
        )
    set_llm_client(fake_llm)

    response = await async_client.post(
        "/api/agent/ask",
        json={"question": "Keep inspecting forever without answering."},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "step_limit_exceeded"
    assert data["step_count"] >= 6


@pytest.mark.asyncio
async def test_agent_ask_repeated_failure_422(async_client: httpx.AsyncClient):
    """Test POST /api/agent/ask returns 422 when repeated identical failing calls occur."""
    fake_llm = FakeLLM()
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(id="tc_1", name="inspect_schema", arguments={"table": "invalid_table"})
            ]
        )
    )
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(id="tc_2", name="inspect_schema", arguments={"table": "invalid_table"})
            ]
        )
    )
    set_llm_client(fake_llm)

    response = await async_client.post(
        "/api/agent/ask",
        json={"question": "Inspect bad table repeatedly."},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "repeated_failure"


@pytest.mark.asyncio
async def test_agent_ask_timeout_504(async_client: httpx.AsyncClient, monkeypatch):
    """Test POST /api/agent/ask returns 504 when per-run timeout expires."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "agent_timeout_seconds", 0.0)

    fake_llm = FakeLLM()
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[ToolCall(id="tc_1", name="inspect_schema", arguments={"table": "users"})]
        )
    )
    set_llm_client(fake_llm)

    response = await async_client.post(
        "/api/agent/ask",
        json={"question": "Test timeout behavior."},
    )
    assert response.status_code == 504
    data = response.json()
    assert data["status"] == "timeout"


@pytest.mark.asyncio
async def test_agent_ask_llm_failure_503(async_client: httpx.AsyncClient):
    """Test POST /api/agent/ask returns 503 when LLM service is unavailable."""
    fake_llm = FakeLLM()
    fake_llm.enqueue_tool_response(LLMUnavailable("OpenAI service unavailable"))
    set_llm_client(fake_llm)

    response = await async_client.post(
        "/api/agent/ask",
        json={"question": "Test LLM failure mapping."},
    )
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "llm_failure"


@pytest.mark.asyncio
async def test_agent_ask_rate_limit_429(async_client: httpx.AsyncClient):
    """Test POST /api/agent/ask returns 429 when IP rate limit is exceeded."""
    fake_llm = FakeLLM(default_tool_response=ToolCompletionResult(content="Answer"))
    set_llm_client(fake_llm)

    # Exhaust rate limit (10 req/min)
    for _ in range(10):
        resp = await async_client.post(
            "/api/agent/ask",
            json={"question": "Rate limit flooding attempt."},
        )
        assert resp.status_code == 200

    # 11th request triggers 429
    throttled = await async_client.post(
        "/api/agent/ask",
        json={"question": "One too many requests."},
    )
    assert throttled.status_code == 429
    assert "Rate limit exceeded" in throttled.json()["detail"]


@pytest.mark.asyncio
async def test_agent_get_run_detail_and_list(async_client: httpx.AsyncClient):
    """Test GET /api/agent/runs/{run_id} and GET /api/agent/runs."""
    fake_llm = FakeLLM()
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(id="tc_hist_1", name="inspect_schema", arguments={"table": "products"})
            ]
        )
    )
    fake_llm.enqueue_tool_response(ToolCompletionResult(content="Found products table schema."))
    set_llm_client(fake_llm)

    # 1. Create a run
    post_resp = await async_client.post(
        "/api/agent/ask",
        json={"question": "Audit test run query."},
    )
    assert post_resp.status_code == 200
    run_id = post_resp.json()["run_id"]

    # 2. Fetch run details
    detail_resp = await async_client.get(f"/api/agent/runs/{run_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["run"]["id"] == run_id
    assert detail_data["run"]["status"] == "completed"
    assert len(detail_data["actions"]) == 1
    assert detail_data["actions"][0]["tool"] == "inspect_schema"

    # 3. Test 404 for unknown run id
    unknown_resp = await async_client.get("/api/agent/runs/nonexistent-run-id-12345")
    assert unknown_resp.status_code == 404

    # 4. Fetch runs list
    list_resp = await async_client.get("/api/agent/runs?limit=10")
    assert list_resp.status_code == 200
    runs_list = list_resp.json()
    assert isinstance(runs_list, list)
    assert any(r["id"] == run_id for r in runs_list)


@pytest.mark.llm
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY") or os.environ.get("RUN_LIVE_LLM_TESTS") != "1",
    reason="Requires live OPENAI_API_KEY and RUN_LIVE_LLM_TESTS=1",
)
@pytest.mark.asyncio
async def test_agent_live_openai(async_client: httpx.AsyncClient):
    """Optional live test against real OpenAI API."""
    response = await async_client.post(
        "/api/agent/ask",
        json={"question": "How many total products are in the catalog?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["final_answer"] is not None
    assert len(data["steps"]) >= 1
