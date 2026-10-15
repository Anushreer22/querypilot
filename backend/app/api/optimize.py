"""FastAPI router for query optimization, plan analysis, index advisor, and isolated benchmarking."""

import asyncio
import logging
import time
import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from app.core.config import settings
from app.db.models import OptimizationHistory
from app.db.session import AppAsyncSessionLocal, bench_engine
from app.schemas.optimizer import (
    OptimizeRequest,
    OptimizeResponse,
)
from app.services.optimizer.benchmark import (
    BenchmarkConcurrencyError,
    BenchmarkError,
    _benchmark_lock,
    run_benchmark,
)
from app.services.optimizer.index_advisor import advise_indexes, get_existing_indexes
from app.services.optimizer.plan_analyzer import PlanAnalysisError, analyze_query_plan
from app.services.sql_validator import validate_sql

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/optimize", tags=["optimizer"])


class InMemoryRateLimiter:
    """Sliding-window in-memory IP rate limiter."""

    def __init__(self, limit_per_minute: int = 5) -> None:
        self.limit_per_minute = limit_per_minute
        self._history: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_ip: str) -> bool:
        """Return True if the client is within the rate limit, otherwise False."""
        now = time.monotonic()
        cutoff = now - 60.0

        async with self._lock:
            timestamps = self._history.get(client_ip, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]
            if len(valid_timestamps) >= self.limit_per_minute:
                self._history[client_ip] = valid_timestamps
                return False
            valid_timestamps.append(now)
            self._history[client_ip] = valid_timestamps
            return True


_optimize_rate_limiter = InMemoryRateLimiter(
    limit_per_minute=settings.rate_limit_optimize_per_minute
)


async def _check_bench_db_reachable() -> bool:
    """Verify that sample_shop_bench copy database is reachable before initiating benchmark."""
    try:
        async with asyncio.timeout(3.0):
            async with bench_engine.connect() as conn:
                await conn.execute(text("SELECT 1;"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("sample_shop_bench unreachable: %s", exc)
        return False


async def _log_optimization_run(
    sql_text: str,
    findings_count: int,
    suggestions_count: int,
    benchmarked: bool,
    improvement_label: str,
    duration_ms: float,
    baseline_median_ms: float | None = None,
    optimized_median_ms: float | None = None,
    speedup_factor: float | None = None,
) -> str | None:
    """Persist optimization audit record in querypilot_app database."""
    run_id = str(uuid.uuid4())
    try:
        async with AppAsyncSessionLocal() as session:
            entry = OptimizationHistory(
                id=run_id,
                sql_text=sql_text[:10000],
                findings_count=findings_count,
                suggestions_count=suggestions_count,
                benchmarked=benchmarked,
                baseline_median_ms=(
                    Decimal(str(round(baseline_median_ms, 2)))
                    if baseline_median_ms is not None
                    else None
                ),
                optimized_median_ms=(
                    Decimal(str(round(optimized_median_ms, 2)))
                    if optimized_median_ms is not None
                    else None
                ),
                speedup_factor=(
                    Decimal(str(round(speedup_factor, 2))) if speedup_factor is not None else None
                ),
                improvement_label=improvement_label[:50],
                duration_ms=Decimal(str(round(duration_ms, 2))),
            )
            session.add(entry)
            await session.commit()
            return run_id
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to persist optimization history to querypilot_app: %s", exc)
        return None


@router.post(
    "",
    response_model=OptimizeResponse,
    summary="Analyze query plan, detect bottlenecks, recommend indexes, and optionally benchmark on safe copy",
    responses={
        200: {
            "description": "Plan analyzed and recommendations generated (with benchmark if requested)"
        },
        409: {"description": "Benchmark lock conflict - another benchmark is currently running"},
        422: {"description": "SQL validation rejected or invalid AST"},
        429: {"description": "Rate limit exceeded (max 5 requests per minute)"},
        503: {"description": "Benchmark copy database (sample_shop_bench) is unavailable"},
    },
)
async def optimize_query(payload: OptimizeRequest, request: Request) -> OptimizeResponse:
    """Analyze query plan bottlenecks and suggest indexes; optionally benchmark on sample_shop_bench."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    start_time = time.perf_counter()

    # 1. Rate limiting
    if not await _optimize_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {settings.rate_limit_optimize_per_minute} optimization requests per minute.",
        )

    # 2. Strict AST SQL validation via Phase 3 validator
    validation = validate_sql(payload.sql)
    if not validation.ok or not validation.sanitized_sql:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"SQL validation rejected: {validation.reason}",
        )

    sanitized_sql = validation.sanitized_sql

    # 3. Query plan analysis against sample_shop (read-only transaction, always rolled back)
    try:
        (
            _,
            root_node,
            findings,
            planning_time_ms,
            execution_time_ms,
            total_cost,
        ) = await analyze_query_plan(sanitized_sql, run_analyze=True)
    except PlanAnalysisError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.error("Unexpected plan analysis failure: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze query plan: {err}",
        ) from err

    # 4. Generate index suggestions
    existing_indexes = await get_existing_indexes()
    suggestions = advise_indexes(findings, existing_indexes=existing_indexes)

    notes: list[str] = [
        "Plan analysis executed with EXPLAIN (ANALYZE, BUFFERS) strictly rolled back in read-only transaction.",
    ]

    benchmark_result = None
    improvement_label = "ESTIMATED" if suggestions else "NONE"

    # 5. Optional benchmarking protocol on sample_shop_bench
    if payload.benchmark:
        if _benchmark_lock.locked():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A query benchmark is already running on sample_shop_bench.",
            )

        # Check bench database connectivity
        bench_ok = await _check_bench_db_reachable()

        if not bench_ok:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Benchmark copy database (sample_shop_bench) is unavailable or unreachable.",
            )

        candidate_suggestion = next((s for s in suggestions if not s.existing), None)
        if not candidate_suggestion:
            notes.append(
                "Benchmark skipped: No non-existing candidate index available to evaluate."
            )
            improvement_label = "NONE"
        else:
            iterations = min(payload.iterations, settings.benchmark_max_iterations)
            try:
                benchmark_result = await run_benchmark(
                    sanitized_sql=sanitized_sql,
                    suggestion=candidate_suggestion,
                    iterations=iterations,
                )
                improvement_label = benchmark_result.improvement_label
                notes.append(
                    f"Benchmarked index {candidate_suggestion.id} across {iterations} iterations on sample_shop_bench."
                )
            except BenchmarkConcurrencyError as err:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(err),
                ) from err
            except BenchmarkError as err:
                logger.error("Benchmark execution error: %s", err)
                notes.append(f"Benchmark failed: {err}")
                improvement_label = "ESTIMATED"
    else:
        notes.append(
            "Benchmark skipped (benchmark=false). Use benchmark=true to measure real speedup on sample_shop_bench."
        )

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    # 6. Record in optimization_history audit ledger
    await _log_optimization_run(
        sql_text=sanitized_sql,
        findings_count=len(findings),
        suggestions_count=len(suggestions),
        benchmarked=payload.benchmark and benchmark_result is not None,
        improvement_label=improvement_label,
        duration_ms=duration_ms,
        baseline_median_ms=benchmark_result.baseline_stats.median_ms if benchmark_result else None,
        optimized_median_ms=benchmark_result.optimized_stats.median_ms
        if benchmark_result
        else None,
        speedup_factor=benchmark_result.speedup_factor if benchmark_result else None,
    )

    plan_summary = (
        f"Execution plan root: {root_node.node_type} (total cost: {total_cost:.1f}). "
        f"Found {len(findings)} bottleneck(s) and {len(suggestions)} index suggestion(s)."
    )

    return OptimizeResponse(
        sql_executed=sanitized_sql,
        planning_time_ms=round(planning_time_ms, 2),
        execution_time_ms=round(execution_time_ms, 2) if execution_time_ms is not None else None,
        total_cost=round(total_cost, 2),
        plan_summary=plan_summary,
        findings=findings,
        suggestions=suggestions,
        benchmark=benchmark_result,
        improvement_label=improvement_label,
        notes=notes,
    )
