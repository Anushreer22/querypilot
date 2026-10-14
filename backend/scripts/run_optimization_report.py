"""Script to execute query plan analysis, isolated benchmarking, and generate docs/OPTIMIZATION_REPORT.md."""

import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("optimization_report")

from app.schemas.optimizer import IndexSuggestion
from app.services.optimizer.benchmark import run_benchmark
from app.services.optimizer.index_advisor import advise_indexes, generate_safe_ddl
from app.services.optimizer.plan_analyzer import analyze_query_plan

BENCHMARK_CASES = [
    {
        "id": "case_1_orders_date_range",
        "title": "Query 1: Chronological Date Range on orders.created_at",
        "category": "Date Range Filter (Missing orders.created_at Index)",
        "sql": """
            SELECT id, user_id, status, total_amount, created_at
            FROM orders
            WHERE created_at >= '2026-01-01'
            ORDER BY created_at DESC
            LIMIT 50;
        """,
        "expected_label": "MEASURED",
    },
    {
        "id": "case_2_order_items_product_join",
        "title": "Query 2: Foreign Key Lookup on order_items.product_id",
        "category": "Foreign Key Join / Aggregate (Missing order_items.product_id Index)",
        "sql": """
            SELECT p.id, p.name, p.category, SUM(oi.quantity) AS total_units, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
            FROM products p
            JOIN order_items oi ON p.id = oi.product_id
            WHERE oi.product_id = 42
            GROUP BY p.id, p.name, p.category;
        """,
        "expected_label": "MEASURED",
    },
    {
        "id": "case_3_products_category",
        "title": "Query 3: Catalog Filtering on products.category",
        "category": "Catalog Dimension Filter (Missing products.category Index)",
        "sql": """
            SELECT id, name, price, stock
            FROM products
            WHERE category = 'Electronics'
            ORDER BY price DESC
            LIMIT 50;
        """,
        "expected_label": "MEASURED",
    },
    {
        "id": "case_4_orders_low_selectivity",
        "title": "Query 4: Low Selectivity Filter on orders.status (Negative Case)",
        "category": "Negative Control: High-Frequency Status Filter with Early LIMIT",
        "sql": """
            SELECT id, user_id, total_amount, status
            FROM orders
            WHERE status = 'delivered'
            LIMIT 50;
        """,
        "force_suggestion": {
            "table": "orders",
            "columns": ["status"],
            "reasoning": "Filter specifies status = 'delivered'. Indexing status on low-cardinality status field.",
        },
        "expected_label": "ESTIMATED",
    },
]


async def run_case(case: dict) -> dict:
    """Run plan analysis, advisor, and safe benchmark for a single query case."""
    raw_sql = case["sql"].strip()
    logger.info("Evaluating %s: %s", case["id"], case["title"])

    # 1. Plan analysis
    (
        sanitized_sql,
        root_node,
        findings,
        planning_time_ms,
        execution_time_ms,
        total_cost,
    ) = await analyze_query_plan(raw_sql, run_analyze=True)

    # 2. Index Advisor
    suggestions = advise_indexes(findings)

    # If force_suggestion is provided (for negative control test)
    candidate: IndexSuggestion | None = None
    if "force_suggestion" in case:
        f_info = case["force_suggestion"]
        idx_name, ddl = generate_safe_ddl(f_info["table"], f_info["columns"])
        candidate = IndexSuggestion(
            id=idx_name,
            table=f_info["table"],
            columns=f_info["columns"],
            ddl=ddl,
            reasoning=f_info["reasoning"],
            estimated_benefit="ESTIMATED: Test low selectivity indexing.",
            estimated_risk="Index overhead on low-cardinality status (~12 MB).",
        )
    elif suggestions:
        candidate = suggestions[0]

    # 3. Benchmark on sample_shop_bench
    bench_result = None
    if candidate:
        logger.info("Running benchmark on candidate index: %s", candidate.id)
        bench_result = await run_benchmark(
            sanitized_sql=sanitized_sql,
            suggestion=candidate,
            iterations=7,
        )

    return {
        "case": case,
        "sanitized_sql": sanitized_sql,
        "root_node": root_node,
        "findings": findings,
        "planning_time_ms": planning_time_ms,
        "execution_time_ms": execution_time_ms,
        "total_cost": total_cost,
        "candidate": candidate,
        "bench": bench_result,
    }


def generate_markdown_report(results: list[dict]) -> str:
    """Format benchmark evaluation data into structured markdown report."""
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# QueryPilot Optimization & Benchmark Report (Phase 6)",
        "",
        f"**Generated**: {now_str}  ",
        "**Target Environment**: PostgreSQL 16 (Docker on Windows)  ",
        "**Production Database**: `sample_shop` (Read-Only, Untouched)  ",
        "**Benchmark Copy Database**: `sample_shop_bench` (Cloned via PostgreSQL Template, Clean Teardown)  ",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        ("Phase 6 provides end-to-end query optimization that combines deep AST-based plan analysis, "
        "evidence-backed index suggestions, and **safe, isolated before/after benchmarking**. "
        "Importantly, QueryPilot strictly separates **MEASURED** performance gains from **ESTIMATED** planner expectations:"),
        "",
        ("- **MEASURED**: Confirmed speedup exceeding the host's measurement noise threshold ($> 2 \\times \\sigma_{\\text{baseline}}$), "
        "verified PostgreSQL query planner index adoption, and byte-for-byte MD5 checksum equivalence on query output."),
        ("- **ESTIMATED**: Theoretical improvements where planner cost decreased, but empirical execution timing fell "
        "within host system virtualization noise, or where the PostgreSQL planner correctly favored a sequential scan due to low selectivity."),
        "",
        "### Summary of Benchmarked Queries",
        "",
        "| ID | Query Pattern | Candidate Index | Baseline Median | Optimized Median | Speedup | Index Used | Result Checksum | Label |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for item in results:
        c = item["case"]
        bench = item["bench"]
        cand = item["candidate"]

        base_med = f"{bench.baseline_stats.median_ms:.1f} ms" if bench else "N/A"
        opt_med = f"{bench.optimized_stats.median_ms:.1f} ms" if bench else "N/A"
        spd = f"{bench.speedup_factor:.1f}x" if bench else "N/A"
        idx_used = "Yes" if bench and bench.index_used else "No"
        chk = "Pass" if bench and bench.results_match else "N/A"
        lbl = bench.improvement_label if bench else "NONE"
        idx_id = cand.id if cand else "None"

        lines.append(
            f"| `{c['id']}` | {c['category']} | `{idx_id}` | {base_med} | {opt_med} | **{spd}** | {idx_used} | {chk} | **`{lbl}`** |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Detailed Case Studies",
        "",
    ])

    for idx, item in enumerate(results, start=1):
        c = item["case"]
        bench = item["bench"]
        cand = item["candidate"]
        findings = item["findings"]

        lines.extend([
            f"### {c['title']}",
            "",
            f"**Category**: {c['category']}  ",
            f"**Expected Outcome**: `{c['expected_label']}`  ",
            f"**Actual Outcome**: **`{bench.improvement_label if bench else 'NONE'}`**  ",
            "",
            "#### SQL Query",
            "```sql",
            item["sanitized_sql"],
            "```",
            "",
            "#### Baseline Query Plan Findings",
            f"- **Planner Cost**: {item['total_cost']:.1f}",
            f"- **Baseline Execution Time**: {item['execution_time_ms']:.2f} ms",
            f"- **Detected Bottlenecks**: {len(findings)}",
        ])

        for f in findings:
            lines.append(f"  - **[{f.severity.upper()}]** `{f.type}` on `{f.table}`: {f.explanation}")

        if cand:
            lines.extend([
                "",
                "#### Suggested Index Recommendation",
                f"- **Index Identifier**: `{cand.id}`",
                f"- **DDL**: `{cand.ddl}`",
                f"- **Reasoning**: {cand.reasoning}",
                f"- **Estimated Risk**: {cand.estimated_risk}",
            ])

        if bench:
            lines.extend([
                "",
                "#### Empirical Benchmark Results (7 Iterations on `sample_shop_bench`)",
                "",
                "| Metric | Baseline (Pre-Index) | Optimized (Post-Index) | Delta / Change |",
                "| :--- | :--- | :--- | :--- |",
                f"| **Median Latency** | {bench.baseline_stats.median_ms:.2f} ms | {bench.optimized_stats.median_ms:.2f} ms | {bench.baseline_stats.median_ms - bench.optimized_stats.median_ms:+.2f} ms |",
                f"| **P95 Latency** | {bench.baseline_stats.p95_ms:.2f} ms | {bench.optimized_stats.p95_ms:.2f} ms | {bench.baseline_stats.p95_ms - bench.optimized_stats.p95_ms:+.2f} ms |",
                f"| **Min Latency** | {bench.baseline_stats.min_ms:.2f} ms | {bench.optimized_stats.min_ms:.2f} ms | {bench.baseline_stats.min_ms - bench.optimized_stats.min_ms:+.2f} ms |",
                f"| **Max Latency** | {bench.baseline_stats.max_ms:.2f} ms | {bench.optimized_stats.max_ms:.2f} ms | {bench.baseline_stats.max_ms - bench.optimized_stats.max_ms:+.2f} ms |",
                f"| **Std. Deviation** ($\\sigma$) | {bench.baseline_stats.stddev_ms:.2f} ms | {bench.optimized_stats.stddev_ms:.2f} ms | Host timing variance |",
                f"| **Speedup Factor** | — | — | **{bench.speedup_factor:.2f}x** |",
                f"| **Plan Adoption** | Heap / Seq Scan | {bench.new_plan_node or 'None'} | Index adopted: {bench.index_used} |",
                f"| **Index Size** | — | {bench.index_size_mb:.2f} MB | On-disk footprint |",
                f"| **Result Equivalence** | MD5 Checksum | MD5 Checksum | **{'Verified Match' if bench.results_match else 'MISMATCH'}** |",
                "",
                f"> **Conclusion**: {bench.conclusion}",
            ])

        lines.extend(["", "---", ""])

    lines.extend([
        "## Statistical Methodology & Noise Protocol",
        "",
        "### Virtualization Timing Variance on Windows (Docker Desktop)",
        ("Because Docker on Windows runs within the WSL2 / Hyper-V hypervisor, microsecond-level database timings "
        "experience host scheduling jitter, I/O caching variance, and dynamic memory allocation noise. "
        "To avoid deceptive performance claims, QueryPilot implements a 4-tier noise barrier:"),
        "",
        "1. **Warm-up Discard**: 2 unmeasured warm-up iterations precede both the baseline and indexed test runs to prime PostgreSQL shared buffers.",
        "2. **Median Filtering**: 7 measured iterations are executed; median and 95th-percentile (p95) metrics are reported to eliminate outlier skew.",
        "3. **Two-Sigma ($2\\sigma$) Decision Barrier**: A performance gain is classified as `MEASURED` if and only if:",
        "   $$\\text{Baseline Median} - \\text{Optimized Median} > 2 \\times \\sigma_{\\text{baseline}} \\quad \\text{and} \\quad \\text{Speedup} > 1.05$$",
        "   If the measured difference is smaller than $2 \\times \\sigma_{\\text{baseline}}$, the speedup is marked as `ESTIMATED` (statistically indistinguishable from noise).",
        "4. **Deterministic MD5 Checksum**: The result set string representation is hashed with MD5 before and after indexing to verify query semantic equivalence.",
        "",
        "## Invariant Guarantees",
        "- **Production Database Untouched**: DDL and benchmark iterations run strictly against `sample_shop_bench`. The production `sample_shop` database remains completely read-only.",
        "- **Zero LLM DDL**: All `CREATE INDEX` statements are constructed deterministically by the application layer using verified schema identifiers. LLM models cannot propose or execute arbitrary SQL DDL.",
        "- **Guaranteed Teardown**: Candidate indexes are dropped in a `finally` block on `sample_shop_bench`, leaving the benchmark environment clean for subsequent tests.",
    ])

    return "\n".join(lines)


async def main():
    logger.info("Starting Phase 6 Optimization Benchmark Run...")
    results = []
    for case in BENCHMARK_CASES:
        res = await run_case(case)
        results.append(res)

    logger.info("Generating docs/OPTIMIZATION_REPORT.md...")
    report_content = generate_markdown_report(results)

    report_path = Path("docs/OPTIMIZATION_REPORT.md")
    report_path.write_text(report_content, encoding="utf-8")
    logger.info("Successfully wrote optimization report to %s", report_path.resolve())


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
