"""Pydantic schemas for Phase 5 agent requests, responses, and run audit."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentAskRequest(BaseModel):
    """Payload for POST /api/agent/ask."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language question to be investigated by the autonomous database agent.",
        examples=["What are the top 5 highest-spending customers and their total order counts?"],
    )


class AgentActionItem(BaseModel):
    """Structured summary of a single tool execution step within an agent run."""

    step: int
    tool: str
    arguments: dict[str, Any]
    status: str  # 'ok', 'error', 'rejected'
    duration_ms: float
    summary: str | None = None


class AgentQueryResult(BaseModel):
    """Capped query execution output returned by the agent."""

    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: float = 0.0
    truncated: bool = False


class AgentAskResponse(BaseModel):
    """Structured response from POST /api/agent/ask."""

    run_id: str
    question: str
    status: str  # 'completed', 'clarification', 'step_limit_exceeded', 'timeout', 'repeated_failure', 'error', 'llm_failure'
    final_answer: str | None = None
    sql: str | None = None
    results: AgentQueryResult | None = None
    steps: list[AgentActionItem] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    step_count: int = 0
    total_duration_ms: float = 0.0


class AgentRunSummary(BaseModel):
    """High-level summary of an agent run."""

    id: str
    question: str
    status: str
    final_answer: str | None = None
    step_count: int
    total_duration_ms: float
    llm_provider: str | None = None
    llm_model: str | None = None
    created_at: datetime


class AgentRunDetailResponse(BaseModel):
    """Full detail of an agent run including all recorded actions."""

    run: AgentRunSummary
    actions: list[AgentActionItem] = Field(default_factory=list)
