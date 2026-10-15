# QueryPilot Evaluation & Benchmark Results

**Date**: 2026-10-15 11:10:41 UTC  
**Model**: `FakeLLM (Deterministic Test Suite)`  
**Commit**: `734024dc036fe8f087ec3dee16915bc47c2ebf24`  
**Benchmark Suite**: 30 Curated Questions (20 Answerable, 5 Ambiguous, 5 Adversarial)  
**Database**: PostgreSQL 16 (sample_shop seeded with ~50k users, 5k products, ~500k orders)  

---

## 1. Executive Comparison

| Metric | Simple Mode (`/api/ask`) | Agent Mode (`/api/agent/ask`) | Target Threshold |
| :--- | :---: | :---: | :---: |
| **Execution Accuracy** (Result Sets) | **100.0%** | **100.0%** | $\ge 85\%$ |
| **Clarification Precision** | **100.0%** | **100.0%** | $\ge 80\%$ |
| **Safe Refusal Rate** | **100.0%** | **100.0%** | $100\%$ |
| **SQL Validity Rate** | **100.0%** | **100.0%** | $\ge 95\%$ |
| **Repair Rate** | **0.0%** | N/A (Agent Multi-Turn) | Baseline Metric |
| **Average Steps / Calls** | 1.0 | **0.83** | $\le 5.0$ |
| **Latency p50** | **61.8 ms** | **61.78 ms** | Informational |
| **Latency p95** | **80.17 ms** | **81.57 ms** | Informational |

---

## 2. Evaluation Methodology

1. **Answerable Questions (20)**:
   - Scored strictly by comparing **result set values** (rows and columns) against hand-verified reference SQL queries.
   - Ignores arbitrary column alias choices.
   - Normalizes floating-point calculations to 2 decimal places.
   - Normalizes row order for unordered queries while respecting strict ordering for `ORDER BY` / `LIMIT` queries.
2. **Ambiguous Questions (5)**:
   - Evaluates whether the system asks clarifying questions rather than guessing or executing hallucinated SQL.
3. **Adversarial Questions (5)**:
   - Evaluates security boundaries against prompt injection, stacked statements, DDL/DML mutation attempts, and system table exfiltration.
   - 100% must be safely refused or rejected by the AST security validator.

---

## 3. Detailed Failure Analysis

All 30 benchmark evaluations passed successfully across both Simple and Agent modes.

---

## 4. Cost & Guardrail Compliance
- **Safety Guardrail**: Maximum evaluation calls capped at 70 calls to prevent API quota drain.
- **AST Validator**: 100% of generated queries passed through Phase 3 AST validation before execution.
- **Role Isolation**: All query executions occurred via `readonly_user` within read-only, rolled-back transactions.
