# QueryPilot

AI database engineer: natural language to safe PostgreSQL SQL, query plan analysis, and measured index optimization.

---

## Architecture Overview

QueryPilot operates with two isolated databases and role separation:
- **`querypilot_app` (Internal State)**: Stores QueryPilot application metadata, audit trails, and agent configurations. Accessed via the **`app_rw`** role.
- **`sample_shop` (Target E-Commerce Data)**: Realistic e-commerce store (`users`, `products`, `orders`, `order_items`) populated with up to ~500k orders and ~1.12M line items. Inspected via the **`readonly_user`** role (strictly enforced `SELECT`-only privileges).
- **Dedicated Port `5436`**: Containerized PostgreSQL 16 mapped to `127.0.0.1:5436` on the host to avoid collisions with ambient Windows PostgreSQL services (on ports 5432-5434).
- **FastAPI Backend**: Python 3.11+ / 3.12, async SQLAlchemy 2, psycopg 3, pydantic-settings, and dual Alembic environments.
- **React Frontend**: Vite + React + TypeScript + Tailwind CSS real-time health indicator dashboard.

---

## Prerequisites

1. **Docker & Docker Compose**: Docker Desktop running.
2. **Python**: 3.11+ (Python 3.12 recommended).
3. **Node.js**: Node 18+ and npm.

---

## Setup & Running

### 1. Environment Configuration

Copy the example environment files at root and in the frontend:

```bash
# Root environment configuration
cp .env.example .env

# Frontend environment configuration
cp frontend/.env.example frontend/.env
```

Review `.env` to verify settings. By default, host port `5436` and loopback `127.0.0.1` are configured:
- `APP_DATABASE_URL=postgresql+psycopg://app_rw:querypilot_app_rw_pass@127.0.0.1:5436/querypilot_app`
- `SHOP_DATABASE_URL=postgresql+psycopg://readonly_user:querypilot_readonly_pass@127.0.0.1:5436/sample_shop`
- `SHOP_ADMIN_DATABASE_URL=postgresql+psycopg://postgres:querypilot_postgres_pass@127.0.0.1:5436/sample_shop`

---

### 2. Start PostgreSQL Container

Launch the database container in detached mode:

```bash
docker compose up -d
```

Verify that the container is healthy:

```bash
docker ps --filter "name=querypilot-postgres"
```

#### Verifying Docker PostgreSQL vs Local Workstation Services
Workstations may already run local PostgreSQL instances on ports 5432-5434. QueryPilot routes all traffic through host port `5436`:
- QueryPilot binds to **host port 5436** (container port 5432).
- Connections point to `127.0.0.1:5436`.
- Confirm container connection and databases:
  ```bash
  docker exec querypilot-postgres psql -U postgres -c "SELECT version();"
  docker exec querypilot-postgres psql -U postgres -c "\l"
  ```

---

### 3. Database Migrations (Dual Alembic Environments)

QueryPilot maintains two independent Alembic migration environments:

#### A. Application Database (`querypilot_app`)
Runs via the `app_rw` role:
```powershell
backend\.venv\Scripts\alembic -c backend\alembic.ini current
backend\.venv\Scripts\alembic -c backend\alembic.ini upgrade head
```

#### B. Target E-Commerce Database (`sample_shop`)
Runs via privileged `postgres` admin connection:
```powershell
backend\.venv\Scripts\alembic -c backend\alembic_shop.ini current
backend\.venv\Scripts\alembic -c backend\alembic_shop.ini upgrade head
```

---

### 4. Seed E-Commerce Data (`sample_shop`)

The high-performance seed script ([`backend/scripts/seed_shop.py`](backend/scripts/seed_shop.py)) uses PostgreSQL streaming `COPY` via psycopg 3 and vectorized in-memory generation.

#### Fast Test Seeding (1k users, 200 products, 5k orders)
```powershell
backend\.venv\Scripts\python.exe backend\scripts\seed_shop.py --small
```

#### Full Realistic Dataset (50k users, 5k products, ~500k orders, ~1.12M items)
```powershell
backend\.venv\Scripts\python.exe backend\scripts\seed_shop.py
```

*Features*:
- **Safety Lock**: Verifies active database is strictly `sample_shop` before running any truncation.
- **Data Integrity**: Automatically verifies that `total_amount == sum(quantity * unit_price)` for 100% of orders.
- **ANALYZE**: Automatically updates query planner statistics upon completion.

---

### 5. Backend Setup & Development Server

1. Create a virtual environment and activate it:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv backend\.venv
     backend\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS**:
     ```bash
     python3 -m venv backend/.venv
     source backend/.venv/bin/activate
     ```

2. Install dependencies:
   ```bash
   pip install -r backend/requirements-dev.txt
   ```

3. Start the FastAPI development server:
   ```powershell
   cd backend
   .\.venv\Scripts\python.exe -m app.main
   ```
   *(Or with Uvicorn CLI on Windows: `.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000 --loop asyncio:SelectorEventLoop`)*

   The backend will be live at [http://127.0.0.1:8000](http://127.0.0.1:8000).
   Interactive OpenAPI docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

### 6. Frontend Setup

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser. The page displays real-time health for the FastAPI backend, `querypilot_app` database, and `sample_shop` database.

---

### 7. Running Automated Tests

Run the complete test suite across health checks, schema constraints, security roles, and seed data integrity:

```powershell
backend\.venv\Scripts\pytest backend\tests -v
```

Tests include:
- `test_health.py`: Health checks against live databases (200) and mocked failure states (503).
- `test_shop_schema.py`: Schema validation, foreign keys, check constraints (negative price/stock/quantity rejection, status whitelist, orphan FK checks).
- `test_shop_permissions.py`: Verifies `readonly_user` can execute `SELECT` but is strictly blocked from `INSERT`, `UPDATE`, `DELETE`, and `DROP TABLE`.
- `test_shop_seed.py`: Runs `--small` seed mode, verifies row counts, and verifies that `orders.total_amount == sum(quantity * unit_price)` for 100% of orders.

---

## Detailed Documentation & Query Profiles

- **Database Schema & Deliberate Index Omissions**: Full Mermaid ER diagrams, constraint rationale, deliberate index omissions, and 10 benchmark query profiles with real execution times can be found in [`docs/DATABASE.md`](docs/DATABASE.md).
- **Architecture Decision Records**: Architectural rationale on database isolation and least privilege can be found in [`DECISIONS.md`](DECISIONS.md).
