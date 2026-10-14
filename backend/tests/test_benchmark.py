"""Unit and integration tests for isolated benchmark runner."""

import math

import pytest
from sqlalchemy import text

from app.db.session import bench_admin_engine
from app.schemas.optimizer import IndexSuggestion
from app.services.optimizer.benchmark import (
    BenchmarkConcurrencyError,
    _benchmark_lock,
    _compute_stats,
    _walk_plan_for_index,
    run_benchmark,
)


def test_compute_stats_calculation():
    """Verify statistical indicator computations (median, p95, min, max, stddev)."""
    # Empty case
    empty_stats = _compute_stats([])
    assert empty_stats.iterations == 0
    assert empty_stats.median_ms == 0.0

    # Non-empty odd case
    timings = [10.0, 12.0, 15.0, 11.0, 14.0]
    stats = _compute_stats(timings)
    assert stats.iterations == 5
    assert stats.min_ms == 10.0
    assert stats.max_ms == 15.0
    assert stats.median_ms == 12.0
    assert stats.timings_ms == [10.0, 11.0, 12.0, 14.0, 15.0]
    # mean is 12.4, variance is ((10-12.4)^2 + (11-12.4)^2 + (12-12.4)^2 + (14-12.4)^2 + (15-12.4)^2) / 4 = 17.2 / 4 = 4.3
    # stddev = sqrt(4.3) = ~2.0736 -> round 2.07
    assert math.isclose(stats.stddev_ms, 2.07, abs_tol=0.05)


def test_walk_plan_for_index():
    """Verify recursive walk correctly discovers index usage within nested plan trees."""
    plan_tree = {
        "Node Type": "Hash Join",
        "Plans": [
            {
                "Node Type": "Seq Scan",
                "Relation Name": "products",
            },
            {
                "Node Type": "Bitmap Heap Scan",
                "Relation Name": "order_items",
                "Plans": [
                    {
                        "Node Type": "Bitmap Index Scan",
                        "Index Name": "idx_order_items_product_id",
                    }
                ],
            },
        ],
    }

    found, node_type = _walk_plan_for_index(plan_tree, "idx_order_items_product_id")
    assert found is True
    assert node_type == "Bitmap Index Scan"

    not_found, _ = _walk_plan_for_index(plan_tree, "idx_non_existent")
    assert not_found is False


@pytest.mark.asyncio
async def test_benchmark_concurrency_lock():
    """Verify single-flight concurrency lock raises BenchmarkConcurrencyError on collision."""
    mock_suggestion = IndexSuggestion(
        id="idx_test_concurrency",
        table="orders",
        columns=["created_at"],
        ddl='CREATE INDEX "idx_test_concurrency" ON "orders" ("created_at");',
        reasoning="Test concurrency",
        estimated_benefit="ESTIMATED",
        estimated_risk="Low",
    )

    # Acquire the lock externally to simulate an active benchmark
    async with _benchmark_lock:
        with pytest.raises(BenchmarkConcurrencyError, match="already running"):
            await run_benchmark(
                sanitized_sql="SELECT id FROM orders LIMIT 5;",
                suggestion=mock_suggestion,
                iterations=3,
            )


@pytest.mark.asyncio
async def test_benchmark_run_and_clean_teardown_on_bench_db():
    """Integration test: Benchmark runs against sample_shop_bench and cleans up index on completion."""
    sql = "SELECT id, product_id, quantity FROM order_items WHERE product_id = 42 LIMIT 100;"
    suggestion = IndexSuggestion(
        id="idx_order_items_product_id_test_bench",
        table="order_items",
        columns=["product_id"],
        ddl='CREATE INDEX "idx_order_items_product_id_test_bench" ON "order_items" ("product_id");',
        reasoning="Index foreign key product_id",
        estimated_benefit="ESTIMATED",
        estimated_risk="Low",
    )

    result = await run_benchmark(
        sanitized_sql=sql,
        suggestion=suggestion,
        iterations=3,
    )

    assert result.candidate_index_name == "idx_order_items_product_id_test_bench"
    assert result.baseline_stats.iterations == 3
    assert result.optimized_stats.iterations == 3
    assert result.results_match is True
    assert result.improvement_label in ("MEASURED", "ESTIMATED")

    # Verify INVARIANT: candidate index was dropped and is NOT left behind in sample_shop_bench
    async with bench_admin_engine.connect() as admin_conn:
        idx_check = await admin_conn.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'idx_order_items_product_id_test_bench';
                """
            )
        )
        assert idx_check.scalar() is None
