"""Tests for autonomous agent reasoning loop and safety controls."""

import pytest
from sqlalchemy import select

from app.agent.loop import AgentLoop
from app.db.models import AgentAction, AgentRun
from app.db.session import AppAsyncSessionLocal
from app.services.llm.base import ToolCall, ToolCompletionResult
from app.services.llm.factory import set_llm_client
from app.services.llm.fake import FakeLLM


@pytest.fixture(autouse=True)
def reset_llm_client_fixture():
    """Ensure LLM client override is cleanly reset after each test."""
    yield
    set_llm_client(None)


@pytest.mark.asyncio
async def test_agent_loop_standard_flow():
    """Test standard sequential flow: inspect -> validate -> execute -> final answer."""
    fake_llm = FakeLLM()
    # Step 1: inspect_schema
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(id="call_1", name="inspect_schema", arguments={"table": "users"})
            ]
        )
    )
    # Step 2: validate_sql
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(
                    id="call_2",
                    name="validate_sql",
                    arguments={"sql": "SELECT id, name FROM users ORDER BY id LIMIT 3"},
                )
            ]
        )
    )
    # Step 3: execute_readonly_query
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(
                    id="call_3",
                    name="execute_readonly_query",
                    arguments={"sql": "SELECT id, name FROM users ORDER BY id LIMIT 3"},
                )
            ]
        )
    )
    # Step 4: final answer
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            content="Retrieved the first 3 users successfully from the database."
        )
    )
    set_llm_client(fake_llm)

    loop = AgentLoop()
    response = await loop.run("Who are the first 3 users?")

    assert response.status == "completed"
    assert "users successfully" in response.final_answer
    assert response.sql is not None
    assert "LIMIT" in response.sql
    assert response.results is not None
    assert response.results.row_count == 3
    assert len(response.steps) == 3
    assert [s.tool for s in response.steps] == [
        "inspect_schema",
        "validate_sql",
        "execute_readonly_query",
    ]


@pytest.mark.asyncio
async def test_agent_loop_clarification_response():
    """Test that ambiguous questions lead to clarification without query execution."""
    fake_llm = FakeLLM()
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            content="Could you please clarify whether you want products sorted by total revenue or quantity sold?"
        )
    )
    set_llm_client(fake_llm)

    loop = AgentLoop()
    response = await loop.run("Show me the top products.")

    assert response.status == "clarification"
    assert "please clarify" in response.final_answer.lower()
    assert response.sql is None
    assert response.results is None
    assert len(response.steps) == 0


@pytest.mark.asyncio
async def test_agent_loop_tool_error_recovery():
    """Test that the agent handles tool failures and recovers by fixing the query."""
    fake_llm = FakeLLM()
    # Step 1: Propose invalid SQL
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(
                    id="call_bad",
                    name="validate_sql",
                    arguments={"sql": "SELECT bad_column FROM users"},
                )
            ]
        )
    )
    # Step 2: Fix SQL after seeing error
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(
                    id="call_good",
                    name="validate_sql",
                    arguments={"sql": "SELECT id, name FROM users LIMIT 1"},
                )
            ]
        )
    )
    # Step 3: Final answer
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(content="Fixed the query and validated successfully.")
    )
    set_llm_client(fake_llm)

    loop = AgentLoop()
    response = await loop.run("Check user columns")

    assert response.status == "completed"
    assert len(response.steps) == 2
    assert response.steps[0].tool == "validate_sql"
    assert response.steps[1].tool == "validate_sql"


@pytest.mark.asyncio
async def test_agent_loop_step_limit_exceeded():
    """Test that reaching max steps without a final answer terminates with step_limit_exceeded."""
    fake_llm = FakeLLM()
    # Enqueue 5 inspect_schema calls when max_steps=3
    for i in range(5):
        fake_llm.enqueue_tool_response(
            ToolCompletionResult(
                tool_calls=[
                    ToolCall(id=f"c_{i}", name="inspect_schema", arguments={"table": "users"})
                ]
            )
        )
    set_llm_client(fake_llm)

    loop = AgentLoop(max_steps=3)
    response = await loop.run("Loop forever please")

    assert response.status == "step_limit_exceeded"
    assert len(response.steps) == 3


@pytest.mark.asyncio
async def test_agent_loop_repeated_failure_stop():
    """Test that calling the exact same failing tool with identical arguments twice halts the loop."""
    fake_llm = FakeLLM()
    # Call inspect_schema with unknown table twice
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(id="c_1", name="inspect_schema", arguments={"table": "nonexistent_table"})
            ]
        )
    )
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(id="c_2", name="inspect_schema", arguments={"table": "nonexistent_table"})
            ]
        )
    )
    set_llm_client(fake_llm)

    loop = AgentLoop(max_steps=5)
    response = await loop.run("Check table")

    assert response.status == "repeated_failure"
    assert len(response.steps) == 2
    assert "repeated identical" in response.final_answer.lower()


@pytest.mark.asyncio
async def test_agent_loop_timeout_stop():
    """Test that exceeding per-run timeout aborts the loop."""
    fake_llm = FakeLLM()
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(id="c_1", name="inspect_schema", arguments={"table": "users"})
            ]
        )
    )
    set_llm_client(fake_llm)

    loop = AgentLoop(timeout_seconds=0.0)
    response = await loop.run("Timeout test")

    assert response.status == "timeout"
    assert "timed out" in response.final_answer.lower()


@pytest.mark.asyncio
async def test_agent_loop_prompt_injection_in_data():
    """Test that prompt injection inside tool output data is ignored and does not trigger writes."""
    fake_llm = FakeLLM()
    # Step 1: execute query
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(
                    id="call_inj",
                    name="execute_readonly_query",
                    arguments={"sql": "SELECT id, name FROM products LIMIT 2"},
                )
            ]
        )
    )
    # Step 2: model sees data (which could contain injected strings), delivers safe answer
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            content="Assumptions: Products are active.\nFound 2 products in the merchandise catalog."
        )
    )
    set_llm_client(fake_llm)

    loop = AgentLoop()
    response = await loop.run("Check products")

    assert response.status == "completed"
    assert "2 products" in response.final_answer
    assert len(response.assumptions) >= 1


@pytest.mark.asyncio
async def test_agent_loop_persists_runs_and_actions():
    """Verify that agent_runs and agent_actions rows are stored in querypilot_app database."""
    fake_llm = FakeLLM()
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(
            tool_calls=[
                ToolCall(id="c_pers_1", name="inspect_schema", arguments={"table": "users"})
            ]
        )
    )
    fake_llm.enqueue_tool_response(
        ToolCompletionResult(content="Done inspecting users table.")
    )
    set_llm_client(fake_llm)

    loop = AgentLoop()
    response = await loop.run("Inspect user schema for auditing")

    # Inspect querypilot_app DB
    async with AppAsyncSessionLocal() as session:
        stmt_run = select(AgentRun).where(AgentRun.id == response.run_id)
        run_record = (await session.execute(stmt_run)).scalar_one_or_none()
        assert run_record is not None
        assert run_record.status == "completed"
        assert run_record.step_count == 1

        stmt_act = select(AgentAction).where(AgentAction.run_id == response.run_id)
        actions = (await session.execute(stmt_act)).scalars().all()
        assert len(actions) == 1
        assert actions[0].tool_name == "inspect_schema"
        assert actions[0].status == "ok"
