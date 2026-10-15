"""Daily LLM usage cap guard to protect public demo budget."""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import QueryHistory
from app.db.session import AppAsyncSessionLocal

logger = logging.getLogger(__name__)


async def check_daily_llm_cap() -> None:
    """Verify that daily query history count from LLM sources has not exceeded daily_llm_call_cap.

    Raises HTTPException(429) if the cap is reached.
    """
    if settings.daily_llm_call_cap <= 0:
        return

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        async with AppAsyncSessionLocal() as session:
            stmt = (
                select(func.count(QueryHistory.id))
                .where(QueryHistory.created_at >= today_start)
                .where(QueryHistory.source.in_(["ask", "agent"]))
            )
            count = (await session.execute(stmt)).scalar() or 0

            if count >= settings.daily_llm_call_cap:
                logger.warning(
                    "Daily LLM call cap reached: %d >= %d",
                    count,
                    settings.daily_llm_call_cap,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Daily public demo query budget reached ({count}/{settings.daily_llm_call_cap} calls today). "
                        "Please try again tomorrow or self-host QueryPilot with your own API key."
                    ),
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to check daily LLM cap: %s", exc)
