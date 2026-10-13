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

---

## ADR 002: AST-Based SQL Validation and Secure Query Execution Architecture

### Context
In Phase 3, QueryPilot introduces schema inspection and arbitrary query execution APIs (`POST /api/query/execute`). These endpoints are designed to accept ad-hoc SQL from end users and AI agents (starting in Phase 4). Executing arbitrary SQL against a relational database introduces critical security risks:
1. **Destructive Operations**: Prompt injections or malicious inputs attempting `DROP`, `DELETE`, `TRUNCATE`, `UPDATE`, or `ALTER`.
2. **Denial-of-Service**: Intentional slow queries (`pg_sleep()`, heavy unbounded joins, or lock hoarding via `FOR UPDATE`).
3. **Data Exfiltration & Snooping**: Reading system catalogs (`pg_catalog`, `information_schema`), file system probes (`pg_read_file()`), or remote connection hooks (`dblink`).
4. **Obfuscation & Bypass**: Regex-based sanitizers frequently fail against SQL syntax nuances (e.g. comments `/* */`, string escapes, nested CTEs, and stacked statements).

### Decision
We implement a four-layer defense-in-depth security model centered around strict Abstract Syntax Tree (AST) validation:

1. **AST-Based Validation via Pinned `sqlglot` (`sqlglot==30.22.0`)**:
   - Disallow regex for security decisions. Parse full queries with PostgreSQL dialect into an AST.
   - Enforce strictly one statement (reject empty and stacked statements).
   - Root statement must be `exp.Select` or `exp.Union`.
   - Walk all AST nodes to reject mutation statements (`Insert`, `Update`, `Delete`, `Drop`, `Alter`, `Create`, `TruncateTable`, `Merge`), data-modifying CTEs, `SELECT ... INTO`, row locking (`Lock`), and information functions (`CurrentUser`, `SessionUser`, `CurrentVersion`).
   - Strict function allowlist: aggregates, math, string, date/time, and window functions.
   - Table allowlist: restricted to `users`, `products`, `orders`, and `order_items` in schema `public`. CTE aliases are tracked and isolated.
   - LIMIT clamping: automatically append `LIMIT 1000` if omitted, clamp limits > 1000 down to 1000, and reject non-literal limit expressions.
   - Execute **ONLY** sanitized SQL regenerated from the AST via `parsed.sql(dialect="postgres")`. Never execute raw input strings.

2. **Explicit Read-Only Transactions**:
   - Execute `SET TRANSACTION READ ONLY;` as the initial statement in every transaction on `sample_shop`.
   - Configure session timeouts: `statement_timeout = 5000ms`, `lock_timeout = 3000ms`, and `idle_in_transaction_session_timeout = 5000ms`.
   - Timeout detection relies strictly on PostgreSQL SQLSTATE codes (`57014` query canceled, `55P03` lock not available) rather than brittle string matching.

3. **Database-Level Role Hardening**:
   - `readonly_user` role has `default_transaction_read_only = on`, `statement_timeout = '5s'`, and `CONNECTION LIMIT 20`.
   - Execution permissions on `pg_sleep(double precision)` are revoked from `PUBLIC` and `readonly_user`.

4. **Independent Audit Ledger**:
   - All query attempts (`success`, `rejected`, `error`, `timeout`) are recorded in `query_history` on `querypilot_app` using the `app_rw` engine.
   - Logging is isolated in a separate transaction; history write failures are trapped and never crash user responses.

### Consequences
- **Robustness**: Complete immunity to comment-based SQL obfuscation, stacked command execution, and unauthorized table access.
- **Deterministic Resource Consumption**: Guaranteed row caps (<= 1000) and strict statement timeouts (<= 5s) prevent runaway queries and OOM crashes.
- **Auditability**: Complete ledger of all query attempts with execution durations and rejection reasons.
- **Strictness**: Highly complex non-standard PostgreSQL features (e.g. table-valued extensions, administrative commands) are intentionally blocked unless added to the explicit allowlists.

---

## ADR 003: LLM Provider Abstraction, Prompt-and-Repair Architecture, and Privacy Controls

### Context
In Phase 4, QueryPilot introduces AI-powered natural language to SQL translation (`POST /api/ask`). Allowing natural language queries to drive database operations creates unique failure modes:
1. **Model Hallucinations & Syntax Mistakes**: Models may invent non-existent column names, use incorrect joins, or format invalid SQL syntax.
2. **Provider Lock-in & Flakiness**: Cloud LLM APIs experience transient rate limits (HTTP 429) and outages (HTTP 5xx). Tight coupling to a proprietary SDK complicates testing and vendor changes.
3. **Data Privacy**: Sending actual customer database rows or sensitive personal data to third-party LLMs introduces severe compliance and privacy risks.
4. **Infinite Repair Loops**: Naive self-healing query flows can loop endlessly or drain tokens if a repair prompt generates another bad query.

### Decision
We implement a robust, privacy-first prompt-and-repair architecture:

1. **LLM Client Abstraction Protocol**:
   - Define a generic `LLMClient` protocol with one primary method: `complete_json(system_prompt, user_prompt, schema) -> dict`.
   - Provide strongly typed exceptions (`LLMTimeout`, `LLMRateLimit`, `LLMInvalidResponse`, `LLMUnavailable`).
   - Implement `OpenAILLMClient` via lightweight direct `httpx.AsyncClient` with exponential backoff on transient errors (HTTP 429, 5xx) with a max of 2 retries. Never retry invalid requests (400) or malformed JSON blindly.
   - Implement `FakeLLM` for deterministic unit and integration testing without live cloud dependencies.
   - Zero credential or raw secret logging.

2. **Temperature 0.0 for Deterministic Code Generation**:
   - Set `llm_temperature = 0.0` by default. SQL generation requires deterministic structural accuracy rather than creative variance.

3. **Compact Schema Context & Zero Row Data**:
   - Only schema metadata (table names, column types, primary keys, foreign keys, and status enum values) is passed to the LLM.
   - Database row data is **never transmitted** to the LLM.
   - Cached in-memory with a 5-minute TTL (`schema_cache_ttl_seconds = 300`) to eliminate database query overhead.

4. **Single Repair Policy**:
   - If an initial query fails validation or execution with a fixable error (syntax, validator rejection, unknown column), allow exactly **ONE** repair attempt.
   - The repair prompt feeds the error message and the failed SQL back to the model.
   - Timeouts and permission errors are **never repaired**.
   - If the repair fails, the API immediately terminates with `422 Unprocessable Content`. Indefinite repair loops are forbidden.

5. **Sanitized SQL Execution Only**:
   - The execution engine executes **ONLY** the AST-regenerated `sanitized_sql` produced by `sqlglot`. Raw LLM output is never passed to PostgreSQL.

6. **Comprehensive Audit Ledger**:
   - All ask outcomes (`success`, `clarification`, `rejected`, `error`, `timeout`, `llm_failure`) are recorded in `query_history` on `querypilot_app` with `source = 'ask'`, capturing original and repaired queries, user question, explanation, and LLM latency.

### Consequences
- **Security & Privacy**: Zero risk of sensitive customer data leaking to third-party model providers. Complete resistance to prompt injection attacks executing arbitrary commands.
- **Predictable Cost & Latency**: Maximum 2 model calls per user query (initial attempt + single repair), capped tokens, and exponential backoff prevent runaway API spend.
- **Deterministic Testing**: `FakeLLM` allows thorough automated coverage of edge cases, repairs, and network failures in under 10 seconds.



