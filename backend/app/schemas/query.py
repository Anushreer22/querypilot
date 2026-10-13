"""Pydantic schemas for query execution, schema inspection, and audit history."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ColumnInfo(BaseModel):
    """Metadata describing a single table column."""

    name: str
    type: str
    nullable: bool
    default: str | None = None


class ForeignKeyInfo(BaseModel):
    """Metadata describing a foreign key relationship."""

    constrained_columns: list[str]
    referred_table: str
    referred_columns: list[str]


class TableInfo(BaseModel):
    """Schema definition for a database table."""

    name: str
    columns: list[ColumnInfo]
    primary_key: list[str]
    foreign_keys: list[ForeignKeyInfo]


class SchemaResponse(BaseModel):
    """Structured response containing all inspected business tables."""

    tables: list[TableInfo]


class ExecuteQueryRequest(BaseModel):
    """Request payload for executing a secure read-only SQL query."""

    sql: str = Field(..., description="SQL query to validate and execute", max_length=10000)
    source: str = Field("manual", description="Origin of the query (e.g. 'manual', 'agent')")
    timeout_ms: int = Field(5000, description="Execution timeout in milliseconds", ge=10, le=30000)


class ExecuteQueryResponse(BaseModel):
    """Result of a successfully executed SQL query."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: float
    limit_injected: bool
    truncated: bool
    sanitized_sql: str


class QueryHistoryItem(BaseModel):
    """Audit entry for an attempted or executed SQL query."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    sql_text: str
    status: str
    duration_ms: float | None = None
    row_count: int | None = None
    error_message: str | None = None
    created_at: datetime


class QueryHistoryResponse(BaseModel):
    """Paginated list of query history entries."""

    items: list[QueryHistoryItem]
    total: int

