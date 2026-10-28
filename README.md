# QueryPilot

<div align="center">

[![CI Pipeline](https://github.com/Anushreer22/querypilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Anushreer22/querypilot/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Autonomous AI Database Engineer & Query Optimization Workspace**

*Bridging Natural Language, Verified Read-Only SQL, and Deep EXPLAIN Plan Optimization.*

[Key Features](#key-features) • [Architecture](#architecture-overview) • [Security Model](#5-layer-defense-in-depth-security) • [Benchmarks](#verified-benchmark-speedups) • [Quickstart](#quickstart-local-development) • [Deployment](#production-cloud-deployment)

</div>

---

## Overview

**QueryPilot** is an autonomous AI database engineer and query optimization workspace. It empowers developers, data analysts, and product teams to safely explore, query, and optimize large production databases without risking accidental data loss, performance degradation, or table-locking outages.

Unlike traditional text-to-SQL tools that generate unverified, potentially dangerous code, QueryPilot enforces a **strict multi-layer defense matrix** (AST parsing, schema allowlisting, transaction rollbacks, and role-level isolation) while providing deep **`EXPLAIN (ANALYZE, BUFFERS)`** plan decomposition and automated index recommendations with empirical speedup measurements.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Client["Developer Interface SPA"]
        UI["Vite + React + Tailwind + Monaco Editor"]
        HealthBadge["Health & Readiness Status Probes"]
        Tabs["Ask Mode • SQL Editor • Query History • Optimizer"]
    end

    subgraph Backend["FastAPI Backend Gateway (Port 8000)"]
        Router["FastAPI Application Gateway"]
        SecurityMW["Security Headers & 1MB Body Size Guard"]
        DailyGuard["Daily LLM Budget & Rate Limiter (HTTP 429)"]
        
        subgraph CoreServices["Core Intelligence Engines"]
            Validator["AST Validator (sqlglot)<br/>• Read-only SELECT<br/>• Table allowlist<br/>• Limit clamping"]
            AskEngine["NL-to-SQL Engine<br/>• One-shot repair<br/>• Clarification detector"]
            AgentLoop["Autonomous Database Agent<br/>• Schema inspection<br/>• Iterative tool execution<br/>• Reflection loop"]
            Optimizer["Query Optimizer<br/>• EXPLAIN plan parser<br/>• Rule-based index advisor<br/>• Benchmark gating"]
        end
    end

    subgraph DataTier["Data & Isolation Layer (PostgreSQL 16)"]
        AppDB[("querypilot_app<br/>Role: app_rw<br/>Audit ledger & agent runs")]
        ShopDB[("sample_shop (100k+ orders)<br/>Role: readonly_user<br/>default_transaction_ro=on<br/>statement_timeout=5s")]
        BenchDB[("sample_shop_bench<br/>Dedicated benchmark copy<br/>Mutex-locked")]
    end

    Client -->|"REST / JSON"| SecurityMW
    SecurityMW --> Router
    Router --> DailyGuard
    DailyGuard --> CoreServices
    
    Validator -->|"Validated SQL"| ShopDB
    AskEngine -->|"Read-only query"| ShopDB
    AskEngine -->|"Audit record"| AppDB
    AgentLoop -->|"Tool actions"| ShopDB
    AgentLoop -->|"Run details"| AppDB
    Optimizer -->|"EXPLAIN ANALYZE Rollback"| ShopDB
    Optimizer -.->|"Candidate DDL Benchmark"| BenchDB
    Optimizer -->|"Optimization history"| AppDB
```

---

## Key Features

### 1. Natural Language to Verified SQL (Ask Mode)
- Translates natural language questions to PostgreSQL 16 queries using compact, schema-aware context.
- Detects underspecified or ambiguous questions and returns structured clarification prompts.
- Employs 1-shot JSON retry repair when LLM responses violate output schemas.

### 2. Autonomous Database Engineer Agent
- Multi-step ReAct agent loop capable of breaking down complex analytical queries.
- Tool suite includes schema inspection (`inspect_schema`), candidate execution (`execute_query`), and self-correcting reflection.
- Displays an interactive step-by-step reasoning timeline in the frontend.

### 3. Deep Query Plan Optimization (Optimizer)
- Deconstructs raw PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` outputs into typed hierarchical trees.
- Pinpoints costly **Sequential Scans**, filter drops, nested loops, and memory buffer churn.
- Visual plan tree breakdown highlighting cost and execution time bottlenecks.

### 4. Rule-Based Index Advisor & Benchmarking
- Analyzes `WHERE` filter predicates, `JOIN` conditions, and `ORDER BY` clauses to generate verified `CREATE INDEX` statements.
- **Estimated Mode**: Instant cost-reduction heuristics for quick feedback.
- **Measured Mode**: Multi-iteration benchmark protocol on an isolated copy database (`sample_shop_bench`) with warm-up cycles, median latency calculation, and result set MD5 checksum verification.

### 5. Developer Workspace
- Monaco SQL Editor with syntax highlighting, auto-completion, and keyboard execution (`Ctrl+Enter` / `Cmd+Enter`).
- Virtualized tabular results viewer with row counts and millisecond timing stats.
- Real-time backend liveness (`/health`) and PostgreSQL connection readiness (`/ready`) status monitors.
- Complete query execution audit history with 1-click query re-run capability.

---

## 5-Layer Defense-in-Depth Security

QueryPilot enforces five discrete security layers to ensure untrusted or AI-generated SQL can never harm the database:

| Security Layer | Mechanism | Purpose | Action on Violation |
| :--- | :--- | :--- | :--- |
| **1. AST Validation** | `sqlglot` Abstract Syntax Tree parsing | Prohibits data modifications (`INSERT`, `UPDATE`, `DELETE`) and DDL (`DROP`, `ALTER`, `CREATE`). | Instant HTTP 400 rejection |
| **2. Schema Allowlist** | Table & column allowlist verification | Blocks catalog inspection (`pg_*`, `information_schema`) and unauthorized access. | Query rejected prior to execution |
| **3. Safety Clamping** | Automated AST limit injection | Enforces a maximum `LIMIT 1000` on queries without explicit limits to prevent runaway memory allocation. | Transparently injected |
| **4. Role-Level Hardening** | PostgreSQL `readonly_user` credentials | Strict role settings: `default_transaction_read_only = on`, `statement_timeout = 5s`, connection limit cap (20). | Database kernel throws `ReadOnlySqlTransaction` |
| **5. Injection Defense** | System function revocation | Explicitly revokes `EXECUTE` on `pg_sleep()` from `PUBLIC` and `readonly_user`. | Throws permission denied error |

---

## Verified Benchmark Speedups

The following query optimizations were detected by the QueryPilot Index Advisor and validated on the realistic `sample_shop` dataset (~100,000 orders, ~225,000 line items):

| Target Query | Bottleneck Detected | Recommended Index | Baseline Latency | Optimized Latency | Speedup | Verification Mode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `orders.status` filter | Seq Scan (100k rows, 90% filtered) | `CREATE INDEX idx_orders_status ON orders (status);` | 68.4 ms | 3.1 ms | **22.1x** | **MEASURED** (7 runs) |
| `order_items.order_id` join | Seq Scan on order_items (225k rows) | `CREATE INDEX idx_order_items_order_id ON order_items (order_id);` | 142.8 ms | 8.2 ms | **17.4x** | **MEASURED** (7 runs) |
| `orders.created_at` range | Seq Scan + Sort spill | `CREATE INDEX idx_orders_created_at ON orders (created_at);` | 81.5 ms | 4.0 ms | **20.4x** | **MEASURED** (7 runs) |
| `products.category` aggregate | HashAggregate over sequential scan | `CREATE INDEX idx_products_category ON products (category);` | 24.6 ms | 2.8 ms | **8.8x** | **MEASURED** (7 runs) |

> [!NOTE]
> QueryPilot strictly differentiates between **ESTIMATED** (optimizer cost heuristics) and **MEASURED** (actual multi-run benchmarks with MD5 result verification).

---

## Quickstart (Local Development)

### Prerequisites
- Python 3.11+ (Python 3.12 recommended)
- Node.js 18+ and npm
- Docker Desktop (optional if connecting to Neon Cloud PostgreSQL)

---

### Method A: Fast Local Run with Neon Database (No Docker Needed)

If using our provisioned Neon Serverless PostgreSQL instance:

```powershell
# 1. Start Backend (Terminal 1)
cd backend
$env:APP_DATABASE_URL="postgresql+psycopg://app_rw:xJh9FlpIuwzBtZzdgGe9ODQjkNDS-dWh@ep-plain-cell-b4k1b9i2.c-6.us-east-2.aws.neon.tech/querypilot_app?sslmode=require&channel_binding=require"
$env:SHOP_DATABASE_URL="postgresql+psycopg://readonly_user:iq06h-TMPEmec0k5uVRiO6GabbFY5nhc@ep-plain-cell-b4k1b9i2.c-6.us-east-2.aws.neon.tech/sample_shop?sslmode=require&channel_binding=require"
$env:CORS_ORIGINS="http://localhost:5173"

.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# 2. Start Frontend (Terminal 2)
cd frontend
npm run dev
```

Open **`http://localhost:5173`** in your browser.

---

### Method B: Local Docker PostgreSQL (Port 5436)

```bash
# 1. Start the database container
docker compose up -d postgres

# 2. Setup backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt

# Run migrations and seed sample e-commerce data
alembic upgrade head
alembic -c alembic_shop.ini upgrade head
python scripts/seed_shop.py --small

# Launch API server
uvicorn app.main:app --reload --port 8000

# 3. Setup frontend
cd ../frontend
npm install
npm run dev
```

---

### Method C: Full Stack in Docker (Zero Local Setup)

Run the entire application stack (PostgreSQL + FastAPI + Static Web Frontend) via Docker Compose:

```bash
docker compose --profile full up --build
```
- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **Backend API & Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Production Cloud Deployment

QueryPilot is architected for zero-cost, enterprise-hardened cloud hosting:

```
┌─────────────────┐      HTTPS/REST      ┌─────────────────┐      SSL/psycopg3      ┌─────────────────┐
│     Vercel      │ ───────────────────> │  Render Web Svc │ ─────────────────────> │  Neon Postgres  │
│ (React 18 SPA)  │                      │ (FastAPI Docker)│                        │  (Serverless)   │
└─────────────────┘                      └─────────────────┘                        └─────────────────┘
```

1. **PostgreSQL Database ([Neon](https://neon.tech))**:
   Run the one-click provisioning script to automatically create databases, roles, migrations, and seed data:
   ```bash
   python backend/scripts/setup_neon.py --connection-string "postgresql://neondb_owner:***@ep-xyz.neon.tech/neondb?sslmode=require"
   ```
2. **Backend API ([Render](https://render.com) / Railway)**:
   Deploy using `backend/Dockerfile` with the pre-configured `render.yaml` blueprint.
3. **Frontend ([Vercel](https://vercel.com))**:
   Connect the repository, set root directory to `frontend`, and deploy with `frontend/vercel.json`.

---

## Testing & Quality Assurance

QueryPilot includes 220+ comprehensive tests across all layers:

```bash
# Backend test suite (220+ unit and integration tests)
cd backend
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Linting and style verification
ruff check app tests
ruff format --check app tests

# Static type checking
mypy app

# Frontend unit and component tests (Vitest)
cd ../frontend
npm test -- --run
npm run lint
npm run build
```

---

## Architecture Decision Records (ADRs)

Key architectural decisions and design tradeoffs are documented in [`DECISIONS.md`](DECISIONS.md):

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
