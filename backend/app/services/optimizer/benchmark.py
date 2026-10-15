"""Benchmark runner comparing query performance before and after index creation on sample_shop_bench."""

import asyncio
import hashlib
import json
import logging
import math
import time
from typing import Any

from sqlalchemy import text

from app.db.session import bench_admin_engine, bench_engine
from app.schemas.optimizer import BenchmarkIterationStats, BenchmarkResult, IndexSuggestion

logger = logging.getLogger(__name__)

# Single-flight concurrency lock to prevent benchmark noise contamination
_benchmark_lock = asyncio.Lock()


class BenchmarkError(Exception):
    """Raised when benchmark execution fails."""


class BenchmarkConcurrencyError(BenchmarkError):
    """Raised when another benchmark is already executing."""


def _compute_stats(timings: list[float]) -> BenchmarkIterationStats:
    """Compute standard statistical indicators (median, p95, min, max, stddev)."""
    if not timings:
        return BenchmarkIterationStats(
            iterations=0,
            timings_ms=[],
            median_ms=0.0,
            p95_ms=0.0,
            min_ms=0.0,
            max_ms=0.0,
            stddev_ms=0.0,
        )

    sorted_t = sorted(timings)
    n = len(sorted_t)

    # Median
    mid = n // 2
    if n % 2 == 1:
        median = sorted_t[mid]
    else:
        median = (sorted_t[mid - 1] + sorted_t[mid]) / 2.0

    # p95 (nearest rank)
    p95_idx = max(0, min(n - 1, math.ceil(0.95 * n) - 1))
    p95 = sorted_t[p95_idx]

    # Stddev
    mean = sum(sorted_t) / n
    variance = sum((x - mean) ** 2 for x in sorted_t) / (n - 1) if n > 1 else 0.0
    stddev = math.sqrt(variance)

    return BenchmarkIterationStats(
        iterations=n,
        timings_ms=[round(t, 2) for t in sorted_t],
        median_ms=round(median, 2),
        p95_ms=round(p95, 2),
        min_ms=round(sorted_t[0], 2),
        max_ms=round(sorted_t[-1], 2),
        stddev_ms=round(stddev, 2),
    )


async def _execute_iteration(
    sanitized_sql: str,
    timeout_ms: int = 5000,
) -> tuple[float, int, str]:
    """Execute a single read-only iteration against sample_shop_bench, measuring time and result checksum."""
    async with bench_engine.connect() as conn:
        await conn.execute(text("SET TRANSACTION READ ONLY;"))
        await conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)};"))
        await conn.execute(text("SET LOCAL lock_timeout = 3000;"))

        start = time.perf_counter()
        cursor = await conn.execute(text(sanitized_sql))
        duration_ms = (time.perf_counter() - start) * 1000.0

        rows = cursor.fetchall() if cursor.returns_rows else []
        row_count = len(rows)

        # Deterministic MD5 hash of string representation of results
        hash_digest = hashlib.md5(str(rows).encode("utf-8")).hexdigest()
        return duration_ms, row_count, hash_digest


def _walk_plan_for_index(plan_node: dict[str, Any], index_name: str) -> tuple[bool, str | None]:
    """Recursively check whether the plan tree uses the specified index."""
    curr_idx = plan_node.get("Index Name", "")
    if curr_idx and curr_idx.lower() == index_name.lower():
        return True, plan_node.get("Node Type")

    for child in plan_node.get("Plans", []):
        if isinstance(child, dict):
            found, ntype = _walk_plan_for_index(child, index_name)
            if found:
                return True, ntype
    return False, None


async def run_benchmark(
    sanitized_sql: str,
    suggestion: IndexSuggestion,
    iterations: int = 7,
    timeout_ms: int = 5000,
) -> BenchmarkResult:
    """Execute the complete benchmarking protocol on sample_shop_bench with candidate index."""
    if _benchmark_lock.locked():
        raise BenchmarkConcurrencyError(
            "A query benchmark is already running on sample_shop_bench."
        )

    async with _benchmark_lock:
        logger.info("Acquired benchmark concurrency lock for %s", suggestion.id)
        candidate_name = suggestion.id
        candidate_ddl = suggestion.ddl

        # 1. Ensure baseline state: Drop candidate index if already lingering on bench DB
        async with bench_admin_engine.connect() as admin_conn:
            await admin_conn.execute(text(f'DROP INDEX IF EXISTS "{candidate_name}";'))
            await admin_conn.commit()

        # 2. Baseline warm-up (2 runs)
        for _ in range(2):
            await _execute_iteration(sanitized_sql, timeout_ms=timeout_ms)

        # 3. Baseline measured iterations
        baseline_timings: list[float] = []
        base_hash = ""
        base_count = 0
        for _ in range(iterations):
            dur, count, digest = await _execute_iteration(sanitized_sql, timeout_ms=timeout_ms)
            baseline_timings.append(dur)
            base_hash = digest
            base_count = count

        baseline_stats = _compute_stats(baseline_timings)

        # 4. Create candidate index on sample_shop_bench
        index_size_mb = 0.0
        index_used = False
        new_plan_node: str | None = None

        try:
            async with bench_admin_engine.connect() as admin_conn:
                logger.info("Applying candidate index DDL on sample_shop_bench: %s", candidate_ddl)
                await admin_conn.execute(text(candidate_ddl))
                await admin_conn.execute(text(f'ANALYZE "{suggestion.table}";'))
                await admin_conn.commit()

                # Measure index disk footprint
                size_res = await admin_conn.execute(
                    text(f"SELECT pg_relation_size('\"{candidate_name}\"');")
                )
                bytes_used = size_res.scalar() or 0
                index_size_mb = round(bytes_used / (1024.0 * 1024.0), 3)

            # 5. Confirm if plan actually uses the index
            async with bench_engine.connect() as conn:
                await conn.execute(text("SET TRANSACTION READ ONLY;"))
                plan_cursor = await conn.execute(text(f"EXPLAIN (FORMAT JSON) {sanitized_sql}"))
                raw_plan_data = plan_cursor.scalar()
                if isinstance(raw_plan_data, str):
                    plan_obj = json.loads(raw_plan_data)
                else:
                    plan_obj = raw_plan_data

                root_plan = plan_obj[0].get("Plan", {}) if isinstance(plan_obj, list) else {}
                index_used, new_plan_node = _walk_plan_for_index(root_plan, candidate_name)

            # 6. Post-index warm-up (2 runs)
            for _ in range(2):
                await _execute_iteration(sanitized_sql, timeout_ms=timeout_ms)

            # 7. Post-index measured iterations
            optimized_timings: list[float] = []
            opt_hash = ""
            opt_count = 0
            for _ in range(iterations):
                dur, count, digest = await _execute_iteration(sanitized_sql, timeout_ms=timeout_ms)
                optimized_timings.append(dur)
                opt_hash = digest
                opt_count = count

            optimized_stats = _compute_stats(optimized_timings)
            results_match = (base_count == opt_count) and (base_hash == opt_hash)

        finally:
            # 8. Invariant: ALWAYS drop the candidate index to leave bench DB clean
            try:
                async with bench_admin_engine.connect() as admin_conn:
                    logger.info(
                        "Tearing down candidate index '%s' on sample_shop_bench", candidate_name
                    )
                    await admin_conn.execute(text(f'DROP INDEX IF EXISTS "{candidate_name}";'))
                    await admin_conn.commit()
            except Exception as drop_err:  # noqa: BLE001
                logger.error("Failed to drop candidate index '%s': %s", candidate_name, drop_err)

        # 9. Statistical Decision Rule (Measured vs Estimated)
        speedup_factor = round(baseline_stats.median_ms / max(optimized_stats.median_ms, 0.01), 2)
        time_saved = baseline_stats.median_ms - optimized_stats.median_ms

        # Exceeds 2x standard deviation of baseline noise
        is_statistically_significant = (
            time_saved > (2.0 * baseline_stats.stddev_ms) and speedup_factor > 1.05
        )

        if index_used and results_match and is_statistically_significant:
            improvement_label = "MEASURED"
            conclusion = (
                f"Statistically significant measured improvement: {speedup_factor}x speedup "
                f"(median {baseline_stats.median_ms:.1f}ms -> {optimized_stats.median_ms:.1f}ms). "
                f"Execution plan shifted to {new_plan_node or 'Index Scan'}."
            )
        elif not index_used:
            improvement_label = "ESTIMATED"
            conclusion = (
                "No measured improvement: The PostgreSQL planner did not use the candidate index "
                "(table scan cost remained lower due to low filter selectivity or small relation size)."
            )
        elif not results_match:
            improvement_label = "ESTIMATED"
            conclusion = "Benchmark invalidated: Result set checksum mismatch between baseline and indexed query."
        else:
            improvement_label = "ESTIMATED"
            conclusion = (
                f"No significant measured improvement: Observed difference ({time_saved:.1f}ms) "
                f"falls within baseline environment noise (±{2.0 * baseline_stats.stddev_ms:.1f}ms)."
            )

        return BenchmarkResult(
            candidate_index_name=candidate_name,
            candidate_ddl=candidate_ddl,
            baseline_stats=baseline_stats,
            optimized_stats=optimized_stats,
            speedup_factor=speedup_factor,
            index_used=index_used,
            new_plan_node=new_plan_node,
            index_size_mb=index_size_mb,
            results_match=results_match,
            improvement_label=improvement_label,
            conclusion=conclusion,
        )
