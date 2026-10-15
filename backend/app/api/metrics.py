"""Metrics endpoint surfacing in-memory operational telemetry and security statistics."""

from typing import Any

from fastapi import APIRouter

from app.core.metrics import metrics_collector

router = APIRouter(tags=["telemetry"])


@router.get(
    "/api/metrics",
    summary="Fetch operational metrics and security statistics",
    description="Returns in-memory telemetry including request counts, route-level latency percentiles (p50/p95), validator rejections, and agent step statistics.",
)
@router.get(
    "/metrics",
    summary="Prometheus / telemetry metrics alias",
    description="Standard alias route for metrics collection systems.",
)
async def get_metrics() -> dict[str, Any]:
    """Return live in-memory telemetry summary."""
    return metrics_collector.get_summary()
