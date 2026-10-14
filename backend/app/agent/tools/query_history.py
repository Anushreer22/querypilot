"""Tool to safely inspect recent query execution history from querypilot_app."""

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.agent.tools.base import Tool
from app.db.models import QueryHistory
from app.db.session import AppAsyncSessionLocal


class GetQueryHistoryArgs(BaseModel):
    """Arguments for get_query_history tool."""

    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of recent query history entries to return (between 1 and 20).",
    )


async def handle_get_query_history(args: GetQueryHistoryArgs) -> dict[str, Any]:
    """Fetch recent query history entries returning safe fields only."""
    safe_limit = min(max(1, args.limit), 20)

    try:
        async with AppAsyncSessionLocal() as session:
            stmt = (
                select(QueryHistory)
                .order_by(desc(QueryHistory.created_at))
                .limit(safe_limit)
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            entries = [
                {
                    "question": r.question,
                    "sql": r.sql_text,
                    "status": r.status,
                    "duration_ms": float(r.duration_ms) if r.duration_ms is not None else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
            return {
                "ok": True,
                "count": len(entries),
                "entries": entries,
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"Failed to retrieve query history: {exc}",
        }


get_query_history_tool = Tool(
    name="get_query_history",
    description="Retrieve recent query execution history entries (up to 20). Returns safe metadata including question, SQL text, status, duration, and timestamp.",
    args_schema=GetQueryHistoryArgs,
    handler=handle_get_query_history,
)
