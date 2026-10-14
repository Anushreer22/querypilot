"""Agent tool to inspect query plans and receive estimated index recommendations."""

from typing import Any

from pydantic import BaseModel, Field

from app.agent.tools.base import Tool
from app.services.optimizer.index_advisor import advise_indexes
from app.services.optimizer.plan_analyzer import PlanAnalysisError, analyze_query_plan


class AnalyzeQueryPlanArgs(BaseModel):
    """Arguments for analyze_query_plan agent tool."""

    sql: str = Field(
        description="The read-only SELECT query to analyze for plan bottlenecks and index opportunities.",
    )


async def handle_analyze_query_plan(args: AnalyzeQueryPlanArgs) -> dict[str, Any]:
    """Execute plan analysis and return findings and estimated suggestions without running DDL or benchmarks."""
    try:
        (
            _sanitized_sql,
            _root_node,
            findings,
            planning_time_ms,
            execution_time_ms,
            total_cost,
        ) = await analyze_query_plan(args.sql, run_analyze=True)

    except PlanAnalysisError as err:
        return {
            "ok": False,
            "error": str(err),
        }

    suggestions = advise_indexes(findings)

    return {
        "ok": True,
        "total_cost": total_cost,
        "planning_time_ms": planning_time_ms,
        "execution_time_ms": execution_time_ms,
        "findings_count": len(findings),
        "findings": [f.model_dump() for f in findings],
        "suggestions_count": len(suggestions),
        "suggestions": [
            {
                "id": s.id,
                "table": s.table,
                "columns": s.columns,
                "ddl": s.ddl,
                "reasoning": s.reasoning,
                "estimated_benefit": s.estimated_benefit,
            }
            for s in suggestions
        ],
        "summary": f"Analyzed plan (cost={total_cost:.1f}): found {len(findings)} bottlenecks, generated {len(suggestions)} index suggestions.",
    }


analyze_query_plan_tool = Tool(
    name="analyze_query_plan",
    description="Analyze the PostgreSQL execution plan of a read-only SQL query, detect sequential scans and bottlenecks, and return estimated index recommendations. Never executes DDL or benchmarks.",
    args_schema=AnalyzeQueryPlanArgs,
    handler=handle_analyze_query_plan,
)
