"""Integration tests for POST /api/optimize endpoint."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.optimize import _optimize_rate_limiter
from app.db.models import OptimizationHistory
from app.db.session import AppAsyncSessionLocal
from app.services.optimizer.benchmark import _benchmark_lock


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear in-memory rate limiter history before and after each test."""
    _optimize_rate_limiter._history.clear()
    yield
    _optimize_rate_limiter._history.clear()


@pytest.mark.asyncio
async def test_optimize_api_no_benchmark_success(async_client: AsyncClient):
    """Test POST /api/optimize without benchmark returns plan findings and recommendations in ~100ms."""
    payload = {
        "sql": "SELECT id, total_amount FROM orders WHERE created_at >= '2026-01-01' LIMIT 50;",
        "benchmark": False,
    }

    response = await async_client.post("/api/optimize", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "SELECT" in data["sql_executed"]
    assert data["total_cost"] > 0
    assert data["benchmark"] is None
    assert data["improvement_label"] in ("ESTIMATED", "NONE")
    assert isinstance(data["findings"], list)
    assert isinstance(data["suggestions"], list)


@pytest.mark.asyncio
async def test_optimize_api_with_benchmark_success(async_client: AsyncClient):
    """Test POST /api/optimize with benchmark=true runs protocol on sample_shop_bench."""
    payload = {
        "sql": "SELECT id, product_id, quantity FROM order_items WHERE product_id = 10 LIMIT 50;",
        "benchmark": True,
        "iterations": 3,
    }

    response = await async_client.post("/api/optimize", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["benchmark"] is not None
    bench = data["benchmark"]
    assert bench["baseline_stats"]["iterations"] == 3
    assert bench["optimized_stats"]["iterations"] == 3
    assert bench["results_match"] is True
    assert bench["improvement_label"] in ("MEASURED", "ESTIMATED")
    assert "sample_shop_bench" in data["notes"][1] or "Benchmarked" in data["notes"][1]


@pytest.mark.asyncio
async def test_optimize_api_invalid_sql_422(async_client: AsyncClient):
    """Test POST /api/optimize rejects mutating or invalid queries with HTTP 422."""
    payload = {
        "sql": "DELETE FROM users WHERE id = 1;",
        "benchmark": False,
    }

    response = await async_client.post("/api/optimize", json=payload)
    assert response.status_code == 422
    assert "SQL validation rejected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_optimize_api_benchmark_lock_conflict_409(async_client: AsyncClient):
    """Test POST /api/optimize returns HTTP 409 when benchmark concurrency lock is held."""
    payload = {
        "sql": "SELECT id FROM orders LIMIT 10;",
        "benchmark": True,
        "iterations": 3,
    }

    async with _benchmark_lock:
        response = await async_client.post("/api/optimize", json=payload)
        assert response.status_code == 409
        assert "already running" in response.json()["detail"]


@pytest.mark.asyncio
async def test_optimize_api_bench_db_unreachable_503(async_client: AsyncClient):
    """Test POST /api/optimize returns HTTP 503 if sample_shop_bench is unreachable."""
    payload = {
        "sql": "SELECT id FROM orders LIMIT 10;",
        "benchmark": True,
        "iterations": 3,
    }

    with patch("app.api.optimize._check_bench_db_reachable", return_value=False):
        response = await async_client.post("/api/optimize", json=payload)
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_optimize_api_rate_limiting_429(async_client: AsyncClient):
    """Test POST /api/optimize enforces 5 requests/minute rate limit with HTTP 429."""
    payload = {
        "sql": "SELECT id FROM users LIMIT 10;",
        "benchmark": False,
    }

    # Execute 5 allowed requests
    for _ in range(5):
        res = await async_client.post("/api/optimize", json=payload)
        assert res.status_code == 200

    # 6th request must trigger rate limit
    res6 = await async_client.post("/api/optimize", json=payload)
    assert res6.status_code == 429
    assert "Rate limit exceeded" in res6.json()["detail"]


@pytest.mark.asyncio
async def test_optimize_api_audit_ledger_persisted(async_client: AsyncClient):
    """Verify that optimization runs are persisted to optimization_history in querypilot_app."""
    payload = {
        "sql": "SELECT id, name FROM products WHERE category = 'Electronics' LIMIT 10;",
        "benchmark": False,
    }

    response = await async_client.post("/api/optimize", json=payload)
    assert response.status_code == 200

    async with AppAsyncSessionLocal() as session:
        stmt = select(OptimizationHistory).order_by(OptimizationHistory.created_at.desc()).limit(1)
        row = (await session.execute(stmt)).scalar_one_or_none()
        assert row is not None
        assert "products" in row.sql_text
        assert row.benchmarked is False
