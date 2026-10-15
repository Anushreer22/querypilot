"""Strict AST-based SQL Validator using sqlglot with postgres dialect.

Guarantees:
- Exactly one statement, no stacked queries.
- Root statement must be SELECT or UNION (including CTEs).
- No data-modifying statements (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, etc.).
- No SELECT INTO or FOR UPDATE/SHARE locking clauses.
- Functions are restricted to a strict allowlist of safe read-only operations.
- Table access is strictly limited to allowed business tables (users, products, orders, order_items).
- CTEs are supported and isolated from arbitrary database tables.
- System catalogs and alternate schemas (pg_*, information_schema) are forbidden.
- LIMIT is enforced (injected or clamped to at most 1000 rows).
- Only AST-regenerated sanitized SQL is returned for execution.
"""

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

# Configurable constraints
DEFAULT_MAX_QUERY_LENGTH = 10_000
DEFAULT_MAX_LIMIT = 1_000

DEFAULT_ALLOWED_TABLES: set[str] = {
    "users",
    "products",
    "orders",
    "order_items",
}

# Safe SQL function allowlist (case-insensitive names)
ALLOWED_FUNCTION_NAMES: set[str] = {
    # Aggregate functions
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "every",
    "bool_and",
    "bool_or",
    # Conditional / Null handling
    "coalesce",
    "nullif",
    "greatest",
    "least",
    # Mathematical functions
    "abs",
    "cbrt",
    "ceil",
    "ceiling",
    "degrees",
    "div",
    "exp",
    "floor",
    "ln",
    "log",
    "mod",
    "pi",
    "power",
    "radians",
    "round",
    "scale",
    "sign",
    "sqrt",
    "trunc",
    "width_bucket",
    # String manipulation
    "ascii",
    "btrim",
    "chr",
    "concat",
    "concat_ws",
    "initcap",
    "left",
    "length",
    "lower",
    "lpad",
    "ltrim",
    "md5",
    "position",
    "repeat",
    "replace",
    "reverse",
    "right",
    "rpad",
    "rtrim",
    "split_part",
    "strpos",
    "substr",
    "substring",
    "to_hex",
    "translate",
    "trim",
    "upper",
    # Date & Time functions
    "age",
    "date_part",
    "date_trunc",
    "extract",
    "now",
    "timeofday",
    "to_char",
    "to_date",
    "to_timestamp",
    # Window functions
    "cume_dist",
    "dense_rank",
    "first_value",
    "lag",
    "last_value",
    "lead",
    "nth_value",
    "ntile",
    "percent_rank",
    "rank",
    "row_number",
    # Type casting
    "cast",
    "try_cast",
}

# Strongly typed AST classes in sqlglot that represent safe operations
ALLOWED_TYPED_CLASSES: tuple[type[exp.Expression], ...] = (
    # Aggregates
    exp.Count,
    exp.Sum,
    exp.Avg,
    exp.Min,
    exp.Max,
    # Conditionals
    exp.Coalesce,
    exp.Nullif,
    exp.Greatest,
    exp.Least,
    exp.Case,
    exp.If,
    # Math
    exp.Abs,
    exp.Ceil,
    exp.Floor,
    exp.Round,
    exp.Sign,
    exp.Sqrt,
    exp.Pow,
    exp.Exp,
    exp.Ln,
    exp.Log,
    # Strings
    exp.Concat,
    exp.ConcatWs,
    exp.Lower,
    exp.Upper,
    exp.Trim,
    exp.Length,
    exp.Substring,
    exp.Replace,
    exp.Repeat,
    exp.Pad,
    exp.StrPosition,
    # Date / Time
    exp.CurrentTimestamp,
    exp.CurrentDate,
    exp.CurrentTime,
    exp.TimestampTrunc,
    exp.Extract,
    exp.TimeToStr,
    exp.StrToTime,
    # Window
    exp.RowNumber,
    exp.Rank,
    exp.DenseRank,
    exp.PercentRank,
    exp.CumeDist,
    exp.Lag,
    exp.Lead,
    exp.FirstValue,
    exp.LastValue,
    exp.NthValue,
    # Cast
    exp.Cast,
    exp.TryCast,
)

# AST nodes strictly forbidden anywhere in the query
FORBIDDEN_MUTATION_CLASSES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Merge,
    exp.Command,
    exp.Set,
    exp.Analyze,
)

# Information functions that leak database/environment details
FORBIDDEN_INFO_CLASSES: tuple[type[exp.Expression], ...] = (
    exp.CurrentUser,
    exp.SessionUser,
    exp.CurrentVersion,
)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating and sanitizing a SQL statement."""

    ok: bool
    reason: str | None = None
    sanitized_sql: str | None = None
    limit_injected: bool = False


def _check_function_node(node: Any) -> tuple[bool, str]:
    """Validate that a function node is on the approved safe allowlist."""
    # Logical connectors (e.g. AND, OR) inherit from exp.Func in sqlglot but are operators
    if isinstance(node, exp.Connector):
        return True, ""

    if isinstance(node, FORBIDDEN_INFO_CLASSES):
        return False, f"Information function '{type(node).__name__}' is not permitted"

    if isinstance(node, exp.Anonymous):
        fn_name = (node.name or "").lower()
        if fn_name in ALLOWED_FUNCTION_NAMES:
            return True, ""
        return False, f"Function '{fn_name}' is not permitted"

    if isinstance(node, exp.Func):
        if type(node) in ALLOWED_TYPED_CLASSES:
            return True, ""
        fn_name = (
            getattr(node, "name", "") or getattr(node, "key", "") or type(node).__name__
        ).lower()
        if fn_name in ALLOWED_FUNCTION_NAMES:
            return True, ""
        return False, f"Function '{fn_name}' is not permitted"

    return True, ""


def validate_sql(
    sql: str,
    allowed_tables: set[str] | None = None,
    max_length: int = DEFAULT_MAX_QUERY_LENGTH,
    max_limit: int = DEFAULT_MAX_LIMIT,
) -> ValidationResult:
    """Inspect and sanitize a SQL query string using sqlglot's PostgreSQL dialect.

    Args:
        sql: Raw SQL string to validate.
        allowed_tables: Set of allowed table names (case-insensitive). Defaults to sample_shop tables.
        max_length: Maximum allowed character length for the query.
        max_limit: Maximum allowed limit clamp.

    Returns:
        ValidationResult indicating success or failure, with sanitized SQL and limit injection status.
    """
    if allowed_tables is None:
        allowed_tables = DEFAULT_ALLOWED_TABLES

    tables_lower: set[str] = {t.lower() for t in allowed_tables}

    # 1. Pre-parse sanity checks
    if not sql or not sql.strip():
        return ValidationResult(ok=False, reason="SQL query cannot be empty or whitespace-only")

    if len(sql) > max_length:
        return ValidationResult(
            ok=False,
            reason=f"SQL query exceeds maximum allowed length of {max_length} characters (received {len(sql)})",
        )

    # 2. Parse into AST
    try:
        parsed_statements = sqlglot.parse(sql, read="postgres")
    except ParseError as e:
        return ValidationResult(ok=False, reason=f"SQL syntax error: {e}")
    except SqlglotError as e:
        return ValidationResult(ok=False, reason=f"Failed to parse SQL: {e}")

    # Filter out empty statements (e.g. from trailing semicolons)
    non_empty_statements = [s for s in parsed_statements if s is not None]

    if not non_empty_statements:
        return ValidationResult(ok=False, reason="SQL query contains no executable statements")

    if len(non_empty_statements) > 1:
        return ValidationResult(
            ok=False,
            reason="Multiple SQL statements are not allowed; stacked queries are strictly prohibited",
        )

    root = non_empty_statements[0]

    # 3. Root statement check: Only SELECT or UNION allowed
    if not isinstance(root, (exp.Select, exp.Union)):
        return ValidationResult(
            ok=False,
            reason=f"Statement type '{type(root).__name__}' is not permitted; only SELECT statements are allowed",
        )

    # 4. Collect CTE aliases in query scope
    cte_names: set[str] = {
        cte.alias.lower() for cte in root.find_all(exp.CTE) if getattr(cte, "alias", None)
    }

    # 5. Walk AST for security constraints
    for node in root.walk():
        # Reject mutation statements (including data-modifying CTEs)
        if isinstance(node, FORBIDDEN_MUTATION_CLASSES):
            return ValidationResult(
                ok=False,
                reason=f"Disallowed statement or command '{type(node).__name__}' found in query",
            )

        # Reject SELECT ... INTO
        if isinstance(node, exp.Into):
            return ValidationResult(
                ok=False, reason="SELECT ... INTO clauses are strictly prohibited"
            )

        # Reject locking clauses (FOR UPDATE, FOR SHARE, etc.)
        if isinstance(node, exp.Lock):
            return ValidationResult(
                ok=False, reason="Row locking clauses (FOR UPDATE/SHARE) are not permitted"
            )

        # Reject information pseudo-columns/functions (e.g. SELECT user, current_user, session_user)
        if isinstance(node, FORBIDDEN_INFO_CLASSES):
            return ValidationResult(
                ok=False,
                reason=f"Information function '{type(node).__name__}' is not permitted",
            )

        if isinstance(node, exp.Column) and not node.table:
            col_name = (node.name or "").lower()
            if col_name in ("user", "current_user", "session_user"):
                return ValidationResult(
                    ok=False,
                    reason=f"Information pseudo-column '{col_name}' is not permitted",
                )

        # Check all function calls against the function allowlist
        if isinstance(node, (exp.Func, exp.Anonymous)):
            ok, reason = _check_function_node(node)
            if not ok:
                return ValidationResult(ok=False, reason=reason)

        # Table-level access control
        if isinstance(node, exp.Table):
            # Reject table-valued functions in FROM/JOIN (e.g. FROM pg_read_file(...), FROM generate_series(...))
            if not isinstance(node.this, exp.Identifier):
                return ValidationResult(
                    ok=False,
                    reason=f"Table-valued functions in FROM or JOIN clauses are not permitted: {node.sql()}",
                )

            table_name = (node.name or "").lower()
            schema_name = (node.db or "").lower()

            # If referencing a CTE in scope
            if table_name in cte_names:
                if schema_name:
                    return ValidationResult(
                        ok=False,
                        reason=f"CTE reference '{table_name}' cannot specify a schema qualification",
                    )
                continue

            # Standard business table check
            if table_name not in tables_lower:
                return ValidationResult(
                    ok=False,
                    reason=f"Access to table '{table_name}' is not permitted; allowed tables: {sorted(tables_lower)}",
                )

            # Schema qualification check (only '' or 'public' allowed)
            if schema_name and schema_name != "public":
                return ValidationResult(
                    ok=False,
                    reason=f"Access to schema '{schema_name}' is not permitted; only 'public' schema is allowed",
                )

            # Database / catalog qualification check
            if getattr(node, "catalog", None):
                return ValidationResult(
                    ok=False,
                    reason="Catalog-qualified table references are not permitted",
                )

        # Subquery limit checks: ensure subquery limits are also literal numbers
        if isinstance(node, exp.Limit) and node is not root.args.get("limit"):
            expr = node.expression
            if not (isinstance(expr, exp.Literal) and expr.is_number):
                return ValidationResult(
                    ok=False,
                    reason="Non-literal LIMIT expressions in subqueries are not permitted",
                )

    # 6. LIMIT enforcement on root query
    limit_injected = False
    root_limit = root.args.get("limit")

    if root_limit is None:
        # No LIMIT clause present: inject LIMIT max_limit
        root.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
        limit_injected = True
    elif isinstance(root_limit, exp.Limit):
        expr = root_limit.expression
        # Check for LIMIT ALL or LIMIT NULL
        if (isinstance(expr, exp.Var) and expr.name.upper() == "ALL") or isinstance(expr, exp.Null):
            root_limit.set("expression", exp.Literal.number(max_limit))
            limit_injected = True
        elif isinstance(expr, exp.Neg):
            return ValidationResult(ok=False, reason="LIMIT cannot be negative")
        elif isinstance(expr, exp.Literal) and expr.is_number:
            try:
                limit_val = int(expr.this)
            except ValueError:
                return ValidationResult(ok=False, reason="Invalid numeric LIMIT value")

            if limit_val < 0:
                return ValidationResult(ok=False, reason="LIMIT cannot be negative")
            if limit_val > max_limit:
                root_limit.set("expression", exp.Literal.number(max_limit))
                limit_injected = True
            else:
                limit_injected = False
        else:
            return ValidationResult(
                ok=False,
                reason="Non-literal LIMIT expressions (e.g. subqueries, parameters) are not permitted",
            )
    elif isinstance(root_limit, exp.Fetch):
        count_expr = root_limit.args.get("count")
        if count_expr is None:
            # FETCH FIRST ROW ONLY -> 1 row <= max_limit
            limit_injected = False
        elif isinstance(count_expr, exp.Neg):
            return ValidationResult(ok=False, reason="FETCH count cannot be negative")
        elif isinstance(count_expr, exp.Literal) and count_expr.is_number:
            try:
                fetch_val = int(count_expr.this)
            except ValueError:
                return ValidationResult(ok=False, reason="Invalid numeric FETCH count")

            if fetch_val < 0:
                return ValidationResult(ok=False, reason="FETCH count cannot be negative")
            if fetch_val > max_limit:
                root_limit.set("count", exp.Literal.number(max_limit))
                limit_injected = True
            else:
                limit_injected = False
        else:
            return ValidationResult(
                ok=False,
                reason="Non-literal FETCH count expressions are not permitted",
            )
    else:
        # Fallback for unexpected limit structure
        root.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
        limit_injected = True

    # 7. Generate clean, sanitized SQL from the AST
    sanitized_sql = root.sql(dialect="postgres")

    return ValidationResult(
        ok=True,
        sanitized_sql=sanitized_sql,
        limit_injected=limit_injected,
    )
