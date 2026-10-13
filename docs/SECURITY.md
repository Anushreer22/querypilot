# QueryPilot Security Architecture & Threat Model

QueryPilot is designed to safely execute analytical SQL queries on behalf of users and automated AI agents. When allowing execution of arbitrary or agent-generated SQL, standard parameterization is insufficient because the query structure itself is dynamic. To defend against SQL injection, data exfiltration, denial-of-service, and server tampering, QueryPilot implements a four-layer **Defense-in-Depth** security model.

---

## 1. Defense-in-Depth Architecture

```
                  Client / Agent Query Request
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Strict AST-Based SQL Validator (sqlglot)           │
│  - Exactly 1 statement (no stacked queries)                 │
│  - Root must be SELECT or UNION                             │
│  - AST walk rejects all mutations & data-modifying CTEs      │
│  - Rejects SELECT INTO and FOR UPDATE/SHARE locking clauses  │
│  - Function allowlist (blocks pg_sleep, pg_read_file, etc.) │
│  - Table allowlist (users, products, orders, order_items)   │
│  - LIMIT injection and clamping (<= 1000 rows)              │
│  - Regenerates sanitized SQL (raw input is discarded)       │
└──────────────────────────────┬──────────────────────────────┘
                               │ Sanitized SQL
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Read-Only Transaction Controls                     │
│  - SET TRANSACTION READ ONLY (initial statement)            │
│  - Per-transaction statement_timeout (up to 5s)             │
│  - Per-transaction lock_timeout (3s)                        │
│  - Per-transaction idle_in_transaction_session_timeout (5s) │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Database Role & Privilege Hardening                │
│  - Dedicated role: readonly_user                            │
│  - Role default: default_transaction_read_only = on         │
│  - Role default: statement_timeout = '5s'                   │
│  - Role connection limit: 20                                │
│  - Revoked: EXECUTE on pg_sleep from PUBLIC, readonly_user  │
│  - Revoked: CREATE on public schema, no write/DDL grants    │
│  - Isolated: No connection privileges on querypilot_app     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Independent Audit Ledger (querypilot_app)          │
│  - Every attempt logged: success | rejected | error | timeout│
│  - Executed on isolated app_rw engine in a separate session │
│  - Audit failures never crash query execution responses     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Layer 1: AST-Based SQL Validator (`app.services.sql_validator`)

Regex-based SQL sanitization is notoriously prone to bypasses (e.g. nested comments, whitespace tricks, quoted keywords, and string concatenation). QueryPilot strictly uses **sqlglot** (pinned to `sqlglot==30.22.0`) parsing with the `postgres` dialect to analyze the Abstract Syntax Tree (AST).

### Core Validation Rules:
1. **Single Statement Enforcement**:
   - `sqlglot.parse` parses the query.
   - Stacked statements (e.g., `SELECT 1; DROP TABLE users;`) and empty statements are immediately rejected.
2. **Root Statement Type**:
   - Must be an AST instance of `exp.Select` or `exp.Union`.
   - Any root command such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `EXPLAIN`, `VACUUM`, `ANALYZE`, or `SET` is rejected.
3. **Deep AST Walk**:
   Every node in the AST (including subqueries and CTE expressions) is inspected:
   - **Mutation Nodes**: `exp.Insert`, `exp.Update`, `exp.Delete`, `exp.Drop`, `exp.Alter`, `exp.Create`, `exp.TruncateTable`, `exp.Merge`, `exp.Command`, `exp.Set`, `exp.Analyze`. This immediately blocks data-modifying CTEs (`WITH deleted AS (DELETE FROM orders ...) SELECT ...`).
   - **Table Creation**: `exp.Into` (`SELECT ... INTO new_table FROM ...`) is forbidden.
   - **Row Locking**: `exp.Lock` (`FOR UPDATE`, `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR KEY SHARE`) is forbidden to prevent denial-of-service locks.
   - **Information Leakage**: `exp.CurrentUser`, `exp.SessionUser`, and `exp.CurrentVersion` (along with bare `user`, `current_user`, `session_user` pseudo-columns) are rejected.
4. **Function Allowlist**:
   QueryPilot uses a strict allowlist. Any function not explicitly allowed is rejected:
   - **Aggregate**: `count`, `sum`, `avg`, `min`, `max`, `every`, `bool_and`, `bool_or`
   - **Conditional / Null**: `coalesce`, `nullif`, `greatest`, `least`, `case`, `if`
   - **Math**: `abs`, `cbrt`, `ceil`, `ceiling`, `degrees`, `div`, `exp`, `floor`, `ln`, `log`, `mod`, `pi`, `power`, `radians`, `round`, `scale`, `sign`, `sqrt`, `trunc`, `width_bucket`
   - **String**: `ascii`, `btrim`, `chr`, `concat`, `concat_ws`, `initcap`, `left`, `length`, `lower`, `lpad`, `ltrim`, `md5`, `position`, `repeat`, `replace`, `reverse`, `right`, `rpad`, `rtrim`, `split_part`, `strpos`, `substr`, `substring`, `to_hex`, `translate`, `trim`, `upper`
   - **Date & Time**: `age`, `date_part`, `date_trunc`, `extract`, `now`, `timeofday`, `to_char`, `to_date`, `to_timestamp`
   - **Window**: `cume_dist`, `dense_rank`, `first_value`, `lag`, `last_value`, `lead`, `nth_value`, `ntile`, `percent_rank`, `rank`, `row_number`
   - **Casting**: `cast`, `try_cast`
   - **Disallowed Functions**: `pg_sleep`, `pg_read_file`, `dblink`, `set_config`, `current_setting`, `pg_terminate_backend`, `lo_import`, `lo_export`, and table-valued functions in `FROM`/`JOIN` (`generate_series`, etc.).
5. **Table Access Controls**:
   - Only `users`, `products`, `orders`, and `order_items` in the `public` schema are permitted.
   - Quoted (`"Users"`) and schema-qualified (`public."users"`) names are normalized.
   - Alternate schemas (`pg_catalog`, `information_schema`, etc.) and database catalog qualifiers are rejected.
   - CTE names are tracked in scope; queries may reference CTE aliases without schema prefixes.
6. **Row Limit Enforcement**:
   - If `LIMIT` is omitted, `LIMIT 1000` is automatically appended (`limit_injected = True`).
   - If `LIMIT > 1000`, `LIMIT ALL`, or `LIMIT NULL`, it is clamped to `LIMIT 1000` (`limit_injected = True`).
   - If `LIMIT <= 1000`, the explicit limit is preserved (`limit_injected = False`).
   - Subquery limits must be literal numbers. Non-literal limits (`LIMIT (SELECT 5)`) and negative limits are rejected.
7. **Regenerated Execution**:
   - The database **never receives the raw input string**. Only `parsed.sql(dialect="postgres")` is passed to the execution engine.

---

## 3. Layer 2: Read-Only Transaction Controls (`app.services.query_executor`)

Even after passing AST validation, every query is wrapped inside an explicit read-only PostgreSQL transaction:

```sql
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = 5000;
SET LOCAL lock_timeout = 3000;
SET LOCAL idle_in_transaction_session_timeout = 5000;
```

- `SET TRANSACTION READ ONLY;` is executed as the very first statement in the transaction. This guarantees that PostgreSQL's internal engine marks the transaction snapshot as read-only.
- Per-query statement timeout defaults to 5,000ms (clamped to max 30,000ms).
- Lock timeout (3,000ms) prevents indefinite waiting on table locks.
- `idle_in_transaction_session_timeout` (5,000ms) terminates dangling client connections.

---

## 4. Layer 3: Database Role and Privilege Hardening

Database security does not rely solely on application middleware. The database engine enforces least-privilege role boundaries:

1. **Role Configuration**:
   ```sql
   ALTER ROLE readonly_user SET default_transaction_read_only = on;
   ALTER ROLE readonly_user SET statement_timeout = '5s';
   ALTER ROLE readonly_user CONNECTION LIMIT 20;
   ```
2. **Revoked Capabilities**:
   - `REVOKE CREATE ON SCHEMA public FROM readonly_user;`
   - `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM readonly_user;`
   - `GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;`
   - `REVOKE EXECUTE ON FUNCTION pg_sleep(double precision) FROM PUBLIC, readonly_user;`
3. **Database Isolation**:
   - `readonly_user` has `REVOKE CONNECT ON DATABASE querypilot_app FROM PUBLIC, readonly_user;`.

---

## 5. Layer 4: Independent Audit Ledger

Every query interaction is permanently recorded in the `query_history` table in `querypilot_app`:

| Field | Description |
|---|---|
| `id` | Primary key (`BIGSERIAL`) |
| `source` | Request origin (e.g. `'manual'`, `'agent'`) |
| `sql_text` | Executed or rejected SQL (truncated to 10,000 chars) |
| `status` | `'success'`, `'rejected'`, `'error'`, or `'timeout'` |
| `duration_ms` | Execution time in milliseconds |
| `row_count` | Number of returned rows |
| `error_message` | Rejection reason or database error (truncated to 2,000 chars) |
| `created_at` | UTC timestamp with timezone (indexed) |

Audit entries are persisted in a separate transaction using the privileged `app_rw` engine. Logging errors are trapped so audit persistence never impacts user response availability.

---

## 6. Threat & Mitigation Matrix

| Threat | Attack Vector | Mitigation Layer | Result |
|---|---|---|---|
| **SQL Injection (Stacked)** | `SELECT * FROM users; DROP TABLE orders;` | Layer 1 (AST Validator) | Rejected (`422 Unprocessable Entity`) |
| **Data Mutation** | `UPDATE users SET name = 'x'` | Layer 1 & Layer 3 | Rejected at AST (`422`) and DB (`25006 ReadOnlySqlTransaction`) |
| **Data-modifying CTE** | `WITH d AS (DELETE FROM orders) SELECT * FROM d` | Layer 1 | Rejected at AST (`422`) |
| **Catalog Snooping** | `SELECT * FROM pg_catalog.pg_class` | Layer 1 & Layer 3 | Rejected (`422 Disallowed Table/Schema`) |
| **Denial of Service (Sleep)** | `SELECT pg_sleep(10)` | Layer 1 & Layer 3 | Rejected at AST (`422`) and DB (`42501 InsufficientPrivilege`) |
| **Denial of Service (Slow Join)**| `CROSS JOIN order_items` | Layer 2 & Layer 3 | Cancelled by `statement_timeout` (`504 Gateway Timeout`) |
| **Row Memory Exhaustion** | `SELECT * FROM order_items` | Layer 1 & Layer 2 | Clamped to `LIMIT 1000` & row capping |
| **Row Locking (Deadlocks)** | `SELECT * FROM orders FOR UPDATE` | Layer 1 | Rejected at AST (`422 Locking clauses prohibited`) |
| **Audit Log Tampering** | Trying to modify `query_history` | Layer 3 | `readonly_user` has zero access to `querypilot_app` |

