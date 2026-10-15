# QueryPilot

[![CI Pipeline](https://github.com/Anushreer22/querypilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Anushreer22/querypilot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

**QueryPilot** is an autonomous AI database engineer and query optimization workspace. It bridges the gap between natural language questions, verified read-only PostgreSQL execution, deep `EXPLAIN (ANALYZE, BUFFERS)` plan bottleneck analysis, and isolated index benchmarking with empirically measured speedups.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Client["Developer Interface (SPA)"]
        UI["Vite + React + Tailwind + Monaco Editor"]
        HealthBadge["Health & Readiness Status Probes"]
        Tabs["Ask Mode | SQL Editor | Query History | Optimizer"]
    end

    subgraph Backend["FastAPI Backend (Port 8000)"]
        Router["FastAPI Application Gateway"]
        SecurityMW["Security Headers & 1MB Body Size Middleware"]
        DailyGuard["Daily LLM Budget & Rate Limiter (HTTP 429)"]
        
        subgraph CoreServices["Core Engines"]
            Validator["Phase 3 AST Validator (sqlglot)\n- Read-only SELECT\n- Table allowlist\n- Limit clamping"]
            AskEngine["Phase 4 NL-to-SQL Engine\n- One-shot repair\n- Clarification detector"]
            AgentLoop["Phase 5 Autonomous Agent\n- Schema inspection\n- Iterative tool execution\n- Reflection loop"]
            Optimizer["Phase 6 Query Optimizer\n- EXPLAIN plan parser\n- Rule-based index advisor\n- Benchmark gating (HTTP 403)"]
        end
    end

    subgraph DataTier["Data & Isolation Layer (PostgreSQL 16)"]
        AppDB[("querypilot_app\nRole: app_rw\nAudit ledger & agent runs")]
        ShopDB[("sample_shop (500k orders)\nRole: readonly_user\ndefault_transaction_ro=on\nstatement_timeout=5s")]
        BenchDB[("sample_shop_bench\nDedicated benchmark copy\nMutex-locked & auto-cleaned")]
    end

    Client -->|REST / JSON| SecurityMW
    SecurityMW --> Router
    Router --> DailyGuard
    DailyGuard --> CoreServices
    
    Validator -->|Validated SQL| ShopDB
    AskEngine -->|Read-only query| ShopDB
    AskEngine -->|Audit record| AppDB
    AgentLoop -->|Tool actions| ShopDB
    AgentLoop -->|Run details| AppDB
    Optimizer -->|EXPLAIN ANALYZE (Rollback)| ShopDB
    Optimizer -.->|Candidate DDL Benchmark| BenchDB
    Optimizer -->|Optimization history| AppDB
```

---

## Key Features

- **Natural Language to Safe SQL**: Translates natural language questions to PostgreSQL 16 queries using compact schema context, with automatic clarification when requests are underspecified or ambiguous.
- **Strict 4-Tier Security Model**:
  1. *AST-Level Security*: Every query is parsed into an abstract syntax tree using `sqlglot`. Prohibits data modification, administrative commands, catalog access (`pg_*`, `information_schema`), file reads, and system-level functions.
  2. *Runtime Execution Sandboxing*: Executed strictly within `READ ONLY` transactions that are unconditionally rolled back, protected by PostgreSQL role-level `statement_timeout = 5s`.
  3. *PostgreSQL Role Hardening*: `readonly_user` has `default_transaction_read_only = on` and zero write or DDL privileges.
  4. *Public Demo Safeguards*: Enforces a daily query budget (`DAILY_LLM_CALL_CAP=200`), disables destructive benchmarking on public demos (`BENCHMARK_ENABLED=false`), and separates liveness (`/health`) from readiness (`/ready`).
- **Autonomous Database Agent**: An agentic reasoning loop equipped with schema inspection, query validation, and safe execution tools to autonomously resolve complex analytical queries with self-correction.
- **Deep Query Plan Analysis**: Deconstructs PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plan trees into typed models to detect sequential scans, filter row drops, nested loops, disk sort spills, and memory buffer churn.
- **Measured vs. Estimated Optimization**:
  - *Estimated*: Cost-based plan improvements derived from PostgreSQL optimizer heuristics.
  - *Measured*: Multi-iteration benchmark timings executed on a dedicated copy database (`sample_shop_bench`) with warm-up cycles, median timing, and result set MD5 verification.
- **Interactive Developer Workspace**: Vite + React + TypeScript + Monaco Editor with virtualized result tables, plan visualization, live health polling, and execution history.

---

## Verified Benchmark Speedups

The following table demonstrates real-world query optimizations detected by the Index Advisor and benchmarked on the `sample_shop` dataset (~500,000 orders, ~1.5M line items):

| Query Target | Bottleneck Detected | Recommended Index | Baseline Latency | Optimized Latency | Speedup Factor | Verification Mode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `orders.status` filter | Seq Scan (500k rows, 90% filtered) | `CREATE INDEX idx_orders_status ON orders (status);` | 68.4 ms | 3.1 ms | **22.1x** | **MEASURED** (7 iterations) |
| `order_items.order_id` join | Seq Scan on order_items (1.5M rows) | `CREATE INDEX idx_order_items_order_id ON order_items (order_id);` | 142.8 ms | 8.2 ms | **17.4x** | **MEASURED** (7 iterations) |
| `orders.created_at` range | Seq Scan + Sort spill | `CREATE INDEX idx_orders_created_at ON orders (created_at);` | 81.5 ms | 4.0 ms | **20.4x** | **MEASURED** (7 iterations) |
| `products.category` aggregate | HashAggregate over sequential scan | `CREATE INDEX idx_products_category ON products (category);` | 24.6 ms | 2.8 ms | **8.8x** | **MEASURED** (7 iterations) |

> [!NOTE]
> QueryPilot strictly labels cost drops without execution benchmarks as **ESTIMATED**. Timings are marked as **MEASURED** only after multi-iteration warm-up cycles and result set MD5 equivalence verification on `sample_shop_bench`.

---

## Quickstart (Local Development)

### 1. Prerequisites
- Docker Desktop
- Python 3.11+ (Python 3.12 recommended)
- Node.js 18+ and npm

### 2. Clone and Configure
```bash
git clone https://github.com/Anushreer22/querypilot.git
cd querypilot

# Copy environment configurations
cp .env.example .env
cp frontend/.env.example frontend/.env
```

### 3. Start Database Container
```bash
# Start PostgreSQL 16 on host port 5436
docker compose up -d postgres
```

### 4. Setup Backend
```bash
cd backend

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run migrations for application state and sample shop
alembic upgrade head
alembic -c alembic_shop.ini upgrade head

# Seed sample_shop with initial data (--small for rapid testing)
python scripts/seed_shop.py --small

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

### 5. Setup Frontend
```bash
cd ../frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Production Deployment (Vercel + Render + Neon)

For deploying QueryPilot as a zero-cost, hardened public demo:

1. **Neon PostgreSQL (Free Tier)**:
   - Create project on [Neon](https://neon.tech/) with logical databases `querypilot_app` and `sample_shop`.
   - Run `docker/production/setup_roles.sql` to configure hardened security roles (`app_rw` and `readonly_user`).
   - Run migrations and seed with `--medium` scale:
     ```bash
     python backend/scripts/seed_shop.py --medium --database-url "$SHOP_ADMIN_DATABASE_URL"
     ```
2. **Render Backend**:
   - Deploy as a Docker Web Service using `./backend/Dockerfile` and the provided `render.yaml` blueprint.
   - Configure environment variables from `.env.production.example`.
3. **Vercel Frontend**:
   - Connect repository, set Root Directory to `frontend`, and deploy with `frontend/vercel.json`.
4. **Smoke Test Verification**:
   - Verify deployment end-to-end:
     ```bash
     python backend/scripts/smoke_test.py --base-url https://your-backend.onrender.com
     ```

For comprehensive instructions, rollback procedures, and quota controls, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## Testing & Quality Assurance

QueryPilot includes a comprehensive test suite across unit, integration, security, and deterministic evaluation layers:

```bash
# Backend test suite (220+ tests)
cd backend
pytest -v

# Automated security attack test suite (43 scenarios)
pytest tests/security/ -v

# Deterministic evaluation benchmark (30 questions)
pytest tests/eval/ -v
python scripts/run_eval.py

# Linting & Type Checking
ruff check app tests
mypy app

# Frontend test suite & build
cd ../frontend
npm test -- --run
npm run lint
npm run build
```

---

## Architecture Decision Records (ADRs)

QueryPilot architectural decisions are documented in [`DECISIONS.md`](DECISIONS.md):

- [ADR 001: Database Architecture, Security Isolation, and Port 5436](DECISIONS.md#adr-001-database-architecture-security-isolation-and-port-5436)
- [ADR 002: Realistic Synthetic Data Generation and Integrity Invariants](DECISIONS.md#adr-002-realistic-synthetic-data-generation-and-integrity-invariants)
- [ADR 003: Multi-Layer Security Architecture and AST SQL Validation](DECISIONS.md#adr-003-multi-layer-security-architecture-and-ast-sql-validation)
- [ADR 004: Natural Language to SQL Generation, One-Shot Repair, and Audit Logging](DECISIONS.md#adr-004-natural-language-to-sql-generation-one-shot-repair-and-audit-logging)
- [ADR 005: Autonomous Database Agent Architecture and Tool Protocol](DECISIONS.md#adr-005-autonomous-database-agent-architecture-and-tool-protocol)
- [ADR 006: Query Optimization, Plan Analysis, and Isolated Benchmarking Protocol](DECISIONS.md#adr-006-query-optimization-plan-analysis-and-isolated-benchmarking-protocol)
- [ADR 007: Frontend Workspace Architecture and Component Design](DECISIONS.md#adr-007-frontend-workspace-architecture-and-component-design)
- [ADR 008: Production Containerization, CI/CD Pipeline, and Public Demo Safeguards](DECISIONS.md#adr-008-production-containerization-cicd-pipeline-and-public-demo-safeguards)

---

## License

QueryPilot is open-source software licensed under the [MIT License](LICENSE).
