"""Pydantic schemas for natural language to SQL /api/ask endpoint."""

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """User question submission payload."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language question to query against the sample_shop database",
    )


class ClarificationResponse(BaseModel):
    """Clarification payload returned when question is ambiguous or underspecified."""

    clarification_question: str


class AskResultPayload(BaseModel):
    """Execution results returned on successful query execution."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: float
    truncated: bool


class AskResponse(BaseModel):
    """Standard response model for /api/ask endpoint."""

    question: str
    sql: str | None = None
    explanation: str
    assumptions: list[str] = Field(default_factory=list)
    results: AskResultPayload | None = None
    repaired: bool = False
    clarification: ClarificationResponse | None = None
    status: str  # 'success', 'clarification', 'rejected', 'error', 'timeout'
