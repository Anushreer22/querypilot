# Architectural Decisions

## ADR 001: Two-Database Architecture and Least-Privilege Role Separation

### Context
QueryPilot is an AI database engineer designed to translate natural language into safe PostgreSQL queries, inspect query plans, and suggest index optimizations. It operates with two distinct areas of concern:
1. **Internal Application State**: QueryPilot's own metadata, migration state, audit logs, and agent evaluation data.
2. **Target User Database**: The external database being analyzed and queried (represented by `sample_shop`).

Exposing a target business database to unrestricted connections or sharing credentials between application internals and user data creates severe security and operational risks, including accidental data corruption, unauthorized schema modifications, or prompt injection exploits attempting `DROP` or `UPDATE` operations.

Additionally, development environments frequently run local database servers (such as Windows PostgreSQL services on 5432-5434). Clear port mapping (`5436:5432`) and explicit loopback addressing (`127.0.0.1`) ensure QueryPilot connects reliably to its dedicated containerized instance.

### Decision
We partition the database architecture into two separate databases and two isolated roles:

1. **Two Distinct Databases**:
   - `querypilot_app`: Stores QueryPilot's internal state, tables, and Alembic migrations.
   - `sample_shop`: The sample eCommerce database containing business data to be inspected.

2. **Two Isolated Roles (Principle of Least Privilege)**:
   - `app_rw`: Has full read/write privileges on `querypilot_app` (schema creation, table updates, and migrations). Connection to `querypilot_app` is restricted to `app_rw`, and connection by other users is revoked.
   - `readonly_user`: Dedicated role for querying `sample_shop`. It has zero write permissions anywhere (`REVOKE CREATE` on schemas, no write permissions). In Phase 2, it will receive strict `SELECT`-only privileges on `sample_shop` tables. It has no connection rights on `querypilot_app`.

3. **Two Independent SQLAlchemy Async Engines**:
   - The backend creates two separate async engines (`app_engine` and `shop_engine`) with separate connection pools and credential bindings. Engines and sessions are never shared.

### Consequences
- **Security & Integrity**: Structural defense-in-depth. Even if an AI-generated query or prompt injection attempts write or DDL operations on `sample_shop`, PostgreSQL enforces permission denial at the database engine level.
- **Operational Clarity**: Clean separation between application migrations (managed via Alembic on `querypilot_app`) and target data schemas.
- **Maintenance**: Requires maintaining two distinct connection URLs and credentials in environment configuration.

