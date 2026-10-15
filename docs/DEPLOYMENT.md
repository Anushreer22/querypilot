# Production Deployment Guide: Public Demo Architecture

This document provides step-by-step instructions for deploying QueryPilot as a zero-cost, hardened public demo stack using **Vercel** (Frontend), **Render** (Backend), and **Neon Serverless PostgreSQL** (Databases).

---

## 1. Architecture Overview

```
                      +-----------------------------+
                      |   Vercel Edge Network       |
                      |   (Vite + React + TS SPA)   |
                      |   https://querypilot.vercel.app
                      +--------------+--------------+
                                     |
                                     | HTTPS / WSS
                                     v
                      +-----------------------------+
                      |   Render Web Service        |
                      |   (Dockerized FastAPI 3.12) |
                      |   BENCHMARK_ENABLED=false   |
                      |   DAILY_LLM_CALL_CAP=200    |
                      +--------------+--------------+
                                     |
                                     | SSL (sslmode=require)
                     +---------------+---------------+
                     |                               |
                     v                               v
       +----------------------------+  +----------------------------+
       | Neon: querypilot_app       |  | Neon: sample_shop          |
       | (Audit, Runs, History)     |  | (Read-Only E-Commerce)     |
       | Role: app_rw (DML allowed) |  | Role: readonly_user        |
       |                            |  | default_transaction_ro=on |
       |                            |  | statement_timeout = 5s     |
       +----------------------------+  +----------------------------+
```

---

## 2. PostgreSQL Setup on Neon (Free Tier)

Neon provides a serverless PostgreSQL instance with a generous 500 MB storage cap and automated compute scaling to zero.

### 2.1. Create Project and Logical Databases
1. Log into the [Neon Console](https://console.neon.tech/) and create a new project named `querypilot`.
2. Select your preferred region (e.g., `AWS us-east-2` to minimize latency to Render's Oregon/Ohio regions).
3. In the **Databases** tab, create two logical databases within the project:
   - `querypilot_app` (stores application state, query history, and agent runs)
   - `sample_shop` (stores synthetic e-commerce data)

### 2.2. Initialize Hardened Security Roles
Connect to the Neon compute instance using the Neon SQL Editor or `psql` as the admin user (`neondb_owner`), and run the production script located at `docker/production/setup_roles.sql`:

```sql
-- Connect to sample_shop and run:
\c sample_shop

-- 1. Create readonly role with strict default settings
CREATE ROLE readonly_user WITH LOGIN PASSWORD 'YOUR_STRONG_READONLY_PASSWORD';
ALTER ROLE readonly_user SET default_transaction_read_only = on;
ALTER ROLE readonly_user SET statement_timeout = '5s';

-- 2. Grant SELECT privileges only
GRANT CONNECT ON DATABASE sample_shop TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- Revoke dangerous permissions
REVOKE CREATE ON SCHEMA public FROM readonly_user;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM readonly_user;

-- 3. Connect to querypilot_app and create app read-write role:
\c querypilot_app

CREATE ROLE app_rw WITH LOGIN PASSWORD 'YOUR_STRONG_APP_RW_PASSWORD';
ALTER ROLE app_rw SET statement_timeout = '10s';

GRANT CONNECT ON DATABASE querypilot_app TO app_rw;
GRANT USAGE, CREATE ON SCHEMA public TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_rw;
```

### 2.3. Run Migrations & Seed Dataset
Run the schema migrations and the `--medium` scale seed script from your local workstation or CI runner targeting the Neon databases (using `sslmode=require`):

```bash
# 1. Migrate querypilot_app schema
export APP_DATABASE_URL="postgresql+psycopg://neondb_owner:YOUR_ADMIN_PASS@ep-xyz.us-east-2.aws.neon.tech/querypilot_app?sslmode=require"
alembic upgrade head

# 2. Migrate sample_shop schema
export SHOP_ADMIN_DATABASE_URL="postgresql+psycopg://neondb_owner:YOUR_ADMIN_PASS@ep-xyz.us-east-2.aws.neon.tech/sample_shop?sslmode=require"
alembic -c alembic_shop.ini upgrade head

# 3. Seed sample_shop with MEDIUM dataset (~65 MB storage footprint)
python backend/scripts/seed_shop.py --medium --database-url "$SHOP_ADMIN_DATABASE_URL"
```

> [!NOTE]
> The `--medium` dataset generates 10,000 users, 1,000 products, 100,000 orders, and ~300,000 order items. This preserves realistic execution plans and sequential scan bottlenecks while staying well below Neon's 500 MB storage cap.

---

## 3. Backend Deployment on Render

### 3.1. Create Service from Dockerfile
1. In the [Render Dashboard](https://dashboard.render.com/), click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Choose **Docker** as the environment:
   - **Dockerfile Path**: `./backend/Dockerfile`
   - **Docker Context**: `./backend`
   - **Instance Type**: Free

### 3.2. Configure Environment Variables
Set the following environment variables in the Render dashboard:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `production` | Activates strict production startup validations |
| `DEMO_MODE` | `true` | Enables demo UI cues and safeguards |
| `BENCHMARK_ENABLED` | `false` | Disables live DDL benchmarking to protect cloud storage |
| `DAILY_LLM_CALL_CAP`| `200` | Hard cap on daily LLM invocations (returns 429 when exhausted) |
| `PORT` | `8000` | Port listened by uvicorn (mapped by Render) |
| `CORS_ORIGINS` | `https://your-app.vercel.app` | Vercel domain (wildcard `*` is strictly blocked in production) |
| `APP_DATABASE_URL` | `postgresql+psycopg://app_rw:PASS@ep-xyz.aws.neon.tech/querypilot_app?sslmode=require` | Application state DB URL |
| `SHOP_DATABASE_URL`| `postgresql+psycopg://readonly_user:PASS@ep-xyz.aws.neon.tech/sample_shop?sslmode=require` | Read-only shop DB URL |
| `LLM_PROVIDER` | `openai` | `openai` or `gemini` |
| `LLM_MODEL` | `gpt-4o-mini` | Cost-effective, high-accuracy model |
| `OPENAI_API_KEY` | `sk-proj-...` | Production OpenAI API key |

### 3.3. Configure Health Probes
- **Health Check Path**: `/health` (Fast liveness check, returns `200 OK`)
- The readiness probe is available at `/ready` for deep database connectivity monitoring.

---

## 4. Frontend Deployment on Vercel

### 4.1. Import Project
1. Log into [Vercel](https://vercel.com/) and click **Add New Project**.
2. Import the `querypilot` repository.
3. Configure the project settings:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

### 4.2. Environment Variables
Add the following environment variables in Vercel:

| Variable | Value |
| :--- | :--- |
| `VITE_API_BASE_URL` | `https://querypilot-backend.onrender.com` |
| `VITE_DEMO_MODE` | `true` |
| `VITE_BENCHMARK_ENABLED` | `false` |

Vercel will automatically deploy and assign your production URL (e.g., `https://querypilot.vercel.app`). Remember to update `CORS_ORIGINS` on Render with this URL!

---

## 5. Verification & Smoke Testing

Once both services are deployed, run the automated smoke test script to verify all endpoints, security filters, and database connections:

```bash
# Run automated smoke test
python backend/scripts/smoke_test.py --base-url https://querypilot-backend.onrender.com
```

### Manual Verification via Curl

```bash
# 1. Liveness Probe (process is responsive)
curl -i https://querypilot-backend.onrender.com/health

# 2. Readiness Probe (both Neon DBs connected)
curl -i https://querypilot-backend.onrender.com/ready

# 3. Schema Catalog Inspection
curl -s https://querypilot-backend.onrender.com/api/schema | jq .

# 4. Safe Read-Only SELECT
curl -X POST https://querypilot-backend.onrender.com/api/query/execute \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT count(*) FROM users;"}'

# 5. Security AST Rejection (Must return 422 Unprocessable Content)
curl -i -X POST https://querypilot-backend.onrender.com/api/query/execute \
  -H "Content-Type: application/json" \
  -d '{"sql": "DROP TABLE users;"}'

# 6. Benchmark Disabled Guard (Must return 403 Forbidden)
curl -i -X POST https://querypilot-backend.onrender.com/api/optimize \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM orders WHERE status = '\''shipped'\'';", "benchmark": true}'
```

---

## 6. Monitoring, Limits & Incident Response

### 6.1. Neon Free-Tier Storage Cap (500 MB)
- In the Neon console, navigate to **Project Settings** -> **Storage**.
- The `--medium` dataset occupies ~65 MB in `sample_shop`.
- Optimization history and query history grow at ~1 KB per query. 100,000 recorded queries consume ~100 MB in `querypilot_app`.
- If storage exceeds 400 MB, truncate old query history:
  ```sql
  \c querypilot_app
  DELETE FROM query_history WHERE created_at < NOW() - INTERVAL '30 days';
  DELETE FROM agent_runs WHERE created_at < NOW() - INTERVAL '30 days';
  ```

### 6.2. LLM Budget Protection
- The public demo enforces `DAILY_LLM_CALL_CAP=200`.
- Once reached, `/api/ask` and `/api/agent/ask` return HTTP 429 Too Many Requests explaining that the daily demo budget has been exhausted.
- The limit resets automatically every day at 00:00:00 UTC.

### 6.3. Rollback Procedure
If a regression occurs on production:
- **Render**: In Render Dashboard -> **Deploys**, select the previous successful build and click **Rollback to this deploy**.
- **Vercel**: In Vercel Deployments, find the previous stable deployment, click the three dots, and select **Promote to Production**.
- **Neon**: If schema migrations need rollback, Neon's Point-in-Time Restore (PITR) allows branching or restoring the database to any state within the retention window with one click.

