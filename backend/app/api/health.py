import logging
from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import app_engine, shop_engine

logger = logging.getLogger(__name__)

router = APIRouter()


async def check_engine_connection(engine: AsyncEngine) -> Literal["ok", "error"]:
    """Execute a simple SELECT 1 query on the given async engine."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            if result.scalar() == 1:
                return "ok"
            return "error"
    except Exception as exc:  # noqa: BLE001 - health check must catch all connection errors
        logger.warning("Database connection check failed: %s", exc)
        return "error"


@router.get("/health")
async def health():
    """Liveness probe: verifies the application server is running."""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """Readiness probe: checks both querypilot_app and sample_shop database connectivity."""
    app_db_status = await check_engine_connection(app_engine)
    shop_db_status = await check_engine_connection(shop_engine)

    is_healthy = (app_db_status == "ok") and (shop_db_status == "ok")
    overall_status = "ok" if is_healthy else "error"

    payload = {
        "status": overall_status,
        "app_db": app_db_status,
        "shop_db": shop_db_status,
    }

    status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=payload)
