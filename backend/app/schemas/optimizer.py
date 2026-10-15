"""Pydantic schemas for query plan analysis, index advisor, and benchmark runner."""

from typing import Any

from pydantic import BaseModel, Field


class PlanNode(BaseModel):
    """Recursive representation of a PostgreSQL EXPLAIN execution plan node."""

    model_config = {"populate_by_name": True}

    node_type: str
    relation_name: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    alias: str | None = None

    startup_cost: float = 0.0
    total_cost: float = 0.0
    plan_rows: float = 0.0
    plan_width: int = 0
    actual_startup_time: float | None = None
    actual_total_time: float | None = None
    actual_rows: float | None = None
    actual_loops: int | None = None
    filter: str | None = None
    rows_removed_by_filter: int | None = None
    index_name: str | None = None
    index_cond: str | None = None
    hash_cond: str | None = None
    join_type: str | None = None
    sort_key: list[str] | None = None
    sort_method: str | None = None
    sort_space_used: int | None = None
    sort_space_type: str | None = None
    shared_hit_blocks: int | None = None
    shared_read_blocks: int | None = None
    plans: list["PlanNode"] = Field(default_factory=list)


class PlanFinding(BaseModel):
    """Bottleneck or optimization finding detected in a query plan."""

    type: str  # 'seq_scan_large_table', 'rows_removed_filter', 'row_estimate_mismatch', etc.
    severity: str  # 'critical', 'warning', 'info'
    plan_node: str
    table: str | None = None
    columns: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    explanation: str


class IndexSuggestion(BaseModel):
    """Application-constructed index recommendation."""

    id: str
    table: str
    columns: list[str]
    index_type: str = "btree"
    predicate: str | None = None
    ddl: str
    reasoning: str
    estimated_benefit: str = "ESTIMATED"
    estimated_risk: str
    existing: bool = False


class BenchmarkIterationStats(BaseModel):
    """Statistical summary across multiple benchmark iterations."""

    iterations: int
    timings_ms: list[float]
    median_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    stddev_ms: float


class BenchmarkResult(BaseModel):
    """Outcome of comparing query performance before and after index creation on sample_shop_bench."""

    candidate_index_name: str
    candidate_ddl: str
    baseline_stats: BenchmarkIterationStats
    optimized_stats: BenchmarkIterationStats
    speedup_factor: float
    index_used: bool
    new_plan_node: str | None = None
    index_size_mb: float = 0.0
    results_match: bool = True
    improvement_label: str  # 'MEASURED' or 'ESTIMATED'
    conclusion: str


class OptimizeRequest(BaseModel):
    """Request payload for POST /api/optimize."""

    sql: str = Field(
        ...,
        min_length=5,
        max_length=10000,
        description="The read-only SELECT query to analyze and optimize.",
    )
    benchmark: bool = Field(
        default=False,
        description="If true, execute safe benchmark protocol on sample_shop_bench copy database.",
    )
    iterations: int = Field(
        default=7,
        ge=3,
        le=15,
        description="Number of measured benchmark iterations per phase (default 7).",
    )


class OptimizeResponse(BaseModel):
    """Response payload from POST /api/optimize."""

    sql_executed: str
    planning_time_ms: float
    execution_time_ms: float | None = None
    total_cost: float
    plan_summary: str
    findings: list[PlanFinding] = Field(default_factory=list)
    suggestions: list[IndexSuggestion] = Field(default_factory=list)
    benchmark: BenchmarkResult | None = None
    improvement_label: str  # 'MEASURED', 'ESTIMATED', 'NONE'
    notes: list[str] = Field(default_factory=list)
