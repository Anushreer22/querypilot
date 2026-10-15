"""Optimizer security and isolation tests.

Verifies:
1. Candidate indexes are NEVER created on the live sample_shop database.
2. Benchmark lock concurrency conflict returns HTTP 409.
3. Candidate indexes on sample_shop_bench are reliably torn down in finally block.
"""

import httpx
import pytest
from sqlalchemy import text

from app.db.session import bench_admin_engine, shop_engine
from app.services.optimizer import benchmark as benchmark_module


async def get_index_names(engine, table_name: str) -> set[str]:
    """Retrieve index names for a specific table."""
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = :tbl;"
            ),
            {"tbl": table_name},
        )
        return {row[0] for row in res.fetchall()}


@pytest.mark.asyncio
async def test_optimizer_never_creates_indexes_on_live_sample_shop(
    async_client: httpx.AsyncClient,
) -> None:
    """Live sample_shop database indexes must remain unchanged during/after optimization runs."""
    indexes_before = await get_index_names(shop_engine, "orders")

    # Send a query that strongly suggests an index on orders(created_at)
    query_sql = (
        "SELECT id, user_id, total_amount FROM orders WHERE created_at >= '2024-01-01' LIMIT 50;"
    )
    resp = await async_client.post(
        "/api/optimize",
        json={"sql": query_sql, "benchmark": False},
    )
    assert resp.status_code == 200

    indexes_after = await get_index_names(shop_engine, "orders")
    assert indexes_before == indexes_after, "sample_shop indexes were mutated by /api/optimize!"


@pytest.mark.asyncio
async def test_optimizer_benchmark_lock_conflict_returns_409(
    async_client: httpx.AsyncClient,
) -> None:
    """When a benchmark is already in-flight, concurrent benchmark requests must return 409."""
    query_sql = "SELECT id, status FROM orders WHERE status = 'delivered' LIMIT 10;"

    # Artificially acquire the module-level benchmark lock
    async with benchmark_module._benchmark_lock:
        resp = await async_client.post(
            "/api/optimize",
            json={"sql": query_sql, "benchmark": True, "iterations": 3},
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"].lower()
        assert "already running" in detail or "conflict" in detail


@pytest.mark.asyncio
async def test_optimizer_candidate_index_torn_down_on_failure(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if benchmarking crashes during execution, candidate index must be dropped from bench DB."""
    # Force _execute_iteration to fail during optimized run
    original_exec = benchmark_module._execute_iteration
    call_count = 0

    async def faulty_iteration(sanitized_sql: str, timeout_ms: int = 5000):
        nonlocal call_count
        call_count += 1
        # Let baseline runs succeed, fail during optimized run
        if call_count > 3:
            raise RuntimeError("Simulated crash during benchmark run")
        return await original_exec(sanitized_sql, timeout_ms=timeout_ms)

    monkeypatch.setattr(benchmark_module, "_execute_iteration", faulty_iteration)

    query_sql = "SELECT id, total_amount FROM orders WHERE status = 'cancelled' LIMIT 5;"
    resp = await async_client.post(
        "/api/optimize",
        json={"sql": query_sql, "benchmark": True, "iterations": 3},
    )
    # The endpoint captures BenchmarkError, logs warning, and sets improvement_label=ESTIMATED
    assert resp.status_code == 200

    # Verify no candidate indexes (starting with idx_ or candidate name) remain on bench DB orders table
    bench_indexes = await get_index_names(bench_admin_engine, "orders")
    assert not any(
        "candidate" in name.lower() or "idx_orders_status" in name.lower() for name in bench_indexes
    )
