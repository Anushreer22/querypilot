# QueryPilot

AI database engineer: natural language to safe PostgreSQL SQL, query plan analysis, and measured index optimization.

---

## Architecture Overview (Phase 1)

Phase 1 provides the core infrastructure and foundational health monitoring:
- **Containerized PostgreSQL 16**: Configured with automated database and role provisioning (`sample_shop` and `querypilot_app`).
- **Port Mapping**: Mapped to host port `5436` (`5436:5432`) to prevent conflicts with ambient PostgreSQL services.
- **FastAPI Backend**: Python 3.11+ / 3.12, async SQLAlchemy 2, psycopg 3, pydantic-settings, and Alembic.
- **React Frontend**: Vite, React, TypeScript, and Tailwind CSS single-page health indicator dashboard.

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

---

### 2. Start PostgreSQL Container

Launch the database container in detached mode:

```bash
docker compose up -d
```

Check the health status of the container:

```bash
docker ps --filter "name=querypilot-postgres"
```

#### Verifying Docker PostgreSQL vs Local Windows Services
If your Windows workstation already runs local PostgreSQL services (such as PostgreSQL on ports 5432-5434), QueryPilot explicitly avoids them:
- QueryPilot binds to **host port 5436** (container port 5432).
- Connections point to `127.0.0.1:5436`.
- To confirm you are connected to the Docker container, run:
  ```bash
  docker exec querypilot-postgres psql -U postgres -c "SELECT version();"
  ```
  and test connecting with the provisioned `app_rw` role:
  ```bash
  docker exec -e PGPASSWORD=querypilot_app_rw_pass querypilot-postgres psql -U app_rw -d querypilot_app -c "SELECT current_database(), current_user;"
  ```

---

### 3. Backend Setup

From the repository root:

1. Create a virtual environment and activate it:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv backend/.venv
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
   *(Or using editable install: `pip install -e "./backend[dev]" -c backend/requirements-dev.txt`)*

3. Verify Alembic status (configured for `querypilot_app`):
   ```powershell
   cd backend
   alembic current
   cd ..
   ```

4. Start the FastAPI development server:
   ```powershell
   cd backend
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   The backend will be live at [http://127.0.0.1:8000](http://127.0.0.1:8000).
   Interactive OpenAPI docs are available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

### 4. Frontend Setup

In a separate terminal:

1. Navigate to the frontend directory and install packages:
   ```bash
   cd frontend
   npm install
   ```

2. Start the Vite development server:
   ```bash
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173) in your browser. The page will display live status for the backend, `querypilot_app` database, and `sample_shop` database.

---

### 5. Running Automated Tests

Run the backend test suite:

```powershell
cd backend
pytest tests -v
```

This tests:
- `test_health_live_dbs_up`: Checks that live database connections return HTTP 200 with `{ "status": "ok", "app_db": "ok", "shop_db": "ok" }`.
- `test_health_mocked_db_failure`: Simulates a single database failure and verifies HTTP 503 response.
- `test_health_mocked_all_db_failure`: Simulates full database failure and verifies HTTP 503 response.

---

## Architectural Decisions

Detailed rationale on database isolation and least-privilege security roles can be found in [DECISIONS.md](DECISIONS.md).
