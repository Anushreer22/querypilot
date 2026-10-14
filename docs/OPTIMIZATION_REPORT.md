# QueryPilot Optimization & Benchmark Report (Phase 6)

**Generated**: 2026-10-14 02:59:45 UTC  
**Target Environment**: PostgreSQL 16 (Docker on Windows)  
**Production Database**: `sample_shop` (Read-Only, Untouched)  
**Benchmark Copy Database**: `sample_shop_bench` (Cloned via PostgreSQL Template, Clean Teardown)  

---

## Executive Summary

Phase 6 provides end-to-end query optimization that combines deep AST-based plan analysis, evidence-backed index suggestions, and **safe, isolated before/after benchmarking**. Importantly, QueryPilot strictly separates **MEASURED** performance gains from **ESTIMATED** planner expectations:

- **MEASURED**: Confirmed speedup exceeding the host's measurement noise threshold ($> 2 \times \sigma_{\text{baseline}}$), verified PostgreSQL query planner index adoption, and byte-for-byte MD5 checksum equivalence on query output.
- **ESTIMATED**: Theoretical improvements where planner cost decreased, but empirical execution timing fell within host system virtualization noise, or where the PostgreSQL planner correctly favored a sequential scan due to low selectivity.

### Summary of Benchmarked Queries

| ID | Query Pattern | Candidate Index | Baseline Median | Optimized Median | Speedup | Index Used | Result Checksum | Label |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `case_1_orders_date_range` | Date Range Filter (Missing orders.created_at Index) | `ix_orders_created_at` | 4.6 ms | 3.1 ms | **1.4x** | Yes | Pass | **`MEASURED`** |
| `case_2_order_items_product_join` | Foreign Key Join / Aggregate (Missing order_items.product_id Index) | `ix_order_items_product_id` | 4.2 ms | 3.5 ms | **1.2x** | Yes | Pass | **`MEASURED`** |
| `case_3_products_category` | Catalog Dimension Filter (Missing products.category Index) | `ix_products_category` | 3.1 ms | 3.2 ms | **1.0x** | No | Pass | **`ESTIMATED`** |
| `case_4_orders_low_selectivity` | Negative Control: High-Frequency Status Filter with Early LIMIT | `ix_orders_status` | 3.0 ms | 2.9 ms | **1.0x** | No | Pass | **`ESTIMATED`** |

---

## Detailed Case Studies

### Query 1: Chronological Date Range on orders.created_at

**Category**: Date Range Filter (Missing orders.created_at Index)  
**Expected Outcome**: `MEASURED`  
**Actual Outcome**: **`MEASURED`**  

#### SQL Query
```sql
SELECT id, user_id, status, total_amount, created_at FROM orders WHERE created_at >= '2026-01-01' ORDER BY created_at DESC LIMIT 50
```

#### Baseline Query Plan Findings
- **Planner Cost**: 209.0
- **Baseline Execution Time**: 5.62 ms
- **Detected Bottlenecks**: 3
  - **[WARNING]** `row_estimate_mismatch` on `None`: Planner miscalculated row count on Sort by 60.4x (50 actual vs 3,022 estimated).
  - **[WARNING]** `seq_scan_large_table` on `orders`: Sequential scan on 'orders' read 3,022 rows (removed 1,978 by filter). Missing index.
  - **[WARNING]** `rows_removed_filter` on `orders`: Seq Scan discarded 1,978 rows after scan using filter '(created_at >= '2026-01-01 00:00:00+00'::timestamp with time zone)'.

#### Suggested Index Recommendation
- **Index Identifier**: `ix_orders_created_at`
- **DDL**: `CREATE INDEX "ix_orders_created_at" ON "orders" ("created_at");`
- **Reasoning**: Plan Seq Scan scanned the orders heap table filtering by date. Indexing 'created_at' eliminates sequential scans for date ranges, rolling windows, and monthly trends.
- **Estimated Risk**: Low maintenance cost; standard single-column B-Tree (~11 MB).

#### Empirical Benchmark Results (7 Iterations on `sample_shop_bench`)

| Metric | Baseline (Pre-Index) | Optimized (Post-Index) | Delta / Change |
| :--- | :--- | :--- | :--- |
| **Median Latency** | 4.57 ms | 3.15 ms | +1.42 ms |
| **P95 Latency** | 4.73 ms | 3.37 ms | +1.36 ms |
| **Min Latency** | 3.67 ms | 3.07 ms | +0.60 ms |
| **Max Latency** | 4.73 ms | 3.37 ms | +1.36 ms |
| **Std. Deviation** ($\sigma$) | 0.44 ms | 0.11 ms | Host timing variance |
| **Speedup Factor** | — | — | **1.45x** |
| **Plan Adoption** | Heap / Seq Scan | Index Scan | Index adopted: True |
| **Index Size** | — | 0.12 MB | On-disk footprint |
| **Result Equivalence** | MD5 Checksum | MD5 Checksum | **Verified Match** |

> **Conclusion**: Statistically significant measured improvement: 1.45x speedup (median 4.6ms -> 3.1ms). Execution plan shifted to Index Scan.

---

### Query 2: Foreign Key Lookup on order_items.product_id

**Category**: Foreign Key Join / Aggregate (Missing order_items.product_id Index)  
**Expected Outcome**: `MEASURED`  
**Actual Outcome**: **`MEASURED`**  

#### SQL Query
```sql
SELECT p.id, p.name, p.category, SUM(oi.quantity) AS total_units, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue FROM products AS p JOIN order_items AS oi ON p.id = oi.product_id WHERE oi.product_id = 42 GROUP BY p.id, p.name, p.category LIMIT 1000
```

#### Baseline Query Plan Findings
- **Planner Cost**: 244.0
- **Baseline Execution Time**: 7.56 ms
- **Detected Bottlenecks**: 3
  - **[WARNING]** `seq_scan_large_table` on `products`: Sequential scan on 'products' read 1 rows (removed 199 by filter). Missing index.
  - **[CRITICAL]** `seq_scan_large_table` on `order_items`: Sequential scan on 'order_items' read 81 rows (removed 11,266 by filter). Missing index.
  - **[WARNING]** `rows_removed_filter` on `order_items`: Seq Scan discarded 11,266 rows after scan using filter '(product_id = 42)'.

#### Suggested Index Recommendation
- **Index Identifier**: `ix_order_items_product_id`
- **DDL**: `CREATE INDEX "ix_order_items_product_id" ON "order_items" ("product_id");`
- **Reasoning**: Foreign key lookup or aggregation on order_items scanned 81.0 rows. Indexing 'product_id' accelerates joins between products and sales line items.
- **Estimated Risk**: Order items are inserted frequently; indexing adds minor write overhead (~25 MB).

#### Empirical Benchmark Results (7 Iterations on `sample_shop_bench`)

| Metric | Baseline (Pre-Index) | Optimized (Post-Index) | Delta / Change |
| :--- | :--- | :--- | :--- |
| **Median Latency** | 4.24 ms | 3.47 ms | +0.77 ms |
| **P95 Latency** | 4.67 ms | 3.69 ms | +0.98 ms |
| **Min Latency** | 3.89 ms | 3.17 ms | +0.72 ms |
| **Max Latency** | 4.67 ms | 3.69 ms | +0.98 ms |
| **Std. Deviation** ($\sigma$) | 0.24 ms | 0.17 ms | Host timing variance |
| **Speedup Factor** | — | — | **1.22x** |
| **Plan Adoption** | Heap / Seq Scan | Bitmap Index Scan | Index adopted: True |
| **Index Size** | — | 0.09 MB | On-disk footprint |
| **Result Equivalence** | MD5 Checksum | MD5 Checksum | **Verified Match** |

> **Conclusion**: Statistically significant measured improvement: 1.22x speedup (median 4.2ms -> 3.5ms). Execution plan shifted to Bitmap Index Scan.

---

### Query 3: Catalog Filtering on products.category

**Category**: Catalog Dimension Filter (Missing products.category Index)  
**Expected Outcome**: `MEASURED`  
**Actual Outcome**: **`ESTIMATED`**  

#### SQL Query
```sql
SELECT id, name, price, stock FROM products WHERE category = 'Electronics' ORDER BY price DESC LIMIT 50
```

#### Baseline Query Plan Findings
- **Planner Cost**: 6.1
- **Baseline Execution Time**: 0.20 ms
- **Detected Bottlenecks**: 1
  - **[WARNING]** `seq_scan_large_table` on `products`: Sequential scan on 'products' read 25 rows (removed 175 by filter). Missing index.

#### Suggested Index Recommendation
- **Index Identifier**: `ix_products_category`
- **DDL**: `CREATE INDEX "ix_products_category" ON "products" ("category");`
- **Reasoning**: Category filtering on products scans all merchandise catalog rows. Indexing 'category' allows direct index lookups.
- **Estimated Risk**: Minimal risk on 5,000 product rows; very small index (<1 MB).

#### Empirical Benchmark Results (7 Iterations on `sample_shop_bench`)

| Metric | Baseline (Pre-Index) | Optimized (Post-Index) | Delta / Change |
| :--- | :--- | :--- | :--- |
| **Median Latency** | 3.11 ms | 3.19 ms | -0.08 ms |
| **P95 Latency** | 10.58 ms | 3.49 ms | +7.09 ms |
| **Min Latency** | 2.93 ms | 2.45 ms | +0.48 ms |
| **Max Latency** | 10.58 ms | 3.49 ms | +7.09 ms |
| **Std. Deviation** ($\sigma$) | 2.80 ms | 0.34 ms | Host timing variance |
| **Speedup Factor** | — | — | **0.97x** |
| **Plan Adoption** | Heap / Seq Scan | None | Index adopted: False |
| **Index Size** | — | 0.02 MB | On-disk footprint |
| **Result Equivalence** | MD5 Checksum | MD5 Checksum | **Verified Match** |

> **Conclusion**: No measured improvement: The PostgreSQL planner did not use the candidate index (table scan cost remained lower due to low filter selectivity or small relation size).

---

### Query 4: Low Selectivity Filter on orders.status (Negative Case)

**Category**: Negative Control: High-Frequency Status Filter with Early LIMIT  
**Expected Outcome**: `ESTIMATED`  
**Actual Outcome**: **`ESTIMATED`**  

#### SQL Query
```sql
SELECT id, user_id, total_amount, status FROM orders WHERE status = 'delivered' LIMIT 50
```

#### Baseline Query Plan Findings
- **Planner Cost**: 1.5
- **Baseline Execution Time**: 0.07 ms
- **Detected Bottlenecks**: 2
  - **[WARNING]** `seq_scan_large_table` on `orders`: Sequential scan on 'orders' read 50 rows (removed 24 by filter). Missing index.
  - **[WARNING]** `row_estimate_mismatch` on `orders`: Planner miscalculated row count on Seq Scan by 72.2x (50 actual vs 3,608 estimated).

#### Suggested Index Recommendation
- **Index Identifier**: `ix_orders_status`
- **DDL**: `CREATE INDEX "ix_orders_status" ON "orders" ("status");`
- **Reasoning**: Filter specifies status = 'delivered'. Indexing status on low-cardinality status field.
- **Estimated Risk**: Index overhead on low-cardinality status (~12 MB).

#### Empirical Benchmark Results (7 Iterations on `sample_shop_bench`)

| Metric | Baseline (Pre-Index) | Optimized (Post-Index) | Delta / Change |
| :--- | :--- | :--- | :--- |
| **Median Latency** | 2.95 ms | 2.89 ms | +0.06 ms |
| **P95 Latency** | 3.25 ms | 3.28 ms | -0.03 ms |
| **Min Latency** | 2.70 ms | 2.43 ms | +0.27 ms |
| **Max Latency** | 3.25 ms | 3.28 ms | -0.03 ms |
| **Std. Deviation** ($\sigma$) | 0.20 ms | 0.29 ms | Host timing variance |
| **Speedup Factor** | — | — | **1.02x** |
| **Plan Adoption** | Heap / Seq Scan | None | Index adopted: False |
| **Index Size** | — | 0.06 MB | On-disk footprint |
| **Result Equivalence** | MD5 Checksum | MD5 Checksum | **Verified Match** |

> **Conclusion**: No measured improvement: The PostgreSQL planner did not use the candidate index (table scan cost remained lower due to low filter selectivity or small relation size).

---

## Statistical Methodology & Noise Protocol

### Virtualization Timing Variance on Windows (Docker Desktop)
Because Docker on Windows runs within the WSL2 / Hyper-V hypervisor, microsecond-level database timings experience host scheduling jitter, I/O caching variance, and dynamic memory allocation noise. To avoid deceptive performance claims, QueryPilot implements a 4-tier noise barrier:

1. **Warm-up Discard**: 2 unmeasured warm-up iterations precede both the baseline and indexed test runs to prime PostgreSQL shared buffers.
2. **Median Filtering**: 7 measured iterations are executed; median and 95th-percentile (p95) metrics are reported to eliminate outlier skew.
3. **Two-Sigma ($2\sigma$) Decision Barrier**: A performance gain is classified as `MEASURED` if and only if:
   $$\text{Baseline Median} - \text{Optimized Median} > 2 \times \sigma_{\text{baseline}} \quad \text{and} \quad \text{Speedup} > 1.05$$
   If the measured difference is smaller than $2 \times \sigma_{\text{baseline}}$, the speedup is marked as `ESTIMATED` (statistically indistinguishable from noise).
4. **Deterministic MD5 Checksum**: The result set string representation is hashed with MD5 before and after indexing to verify query semantic equivalence.

## Invariant Guarantees
- **Production Database Untouched**: DDL and benchmark iterations run strictly against `sample_shop_bench`. The production `sample_shop` database remains completely read-only.
- **Zero LLM DDL**: All `CREATE INDEX` statements are constructed deterministically by the application layer using verified schema identifiers. LLM models cannot propose or execute arbitrary SQL DDL.
- **Guaranteed Teardown**: Candidate indexes are dropped in a `finally` block on `sample_shop_bench`, leaving the benchmark environment clean for subsequent tests.