"""Unit tests for strict AST-based SQL Validator."""


from app.services.sql_validator import validate_sql


class TestSqlValidatorAllowedQueries:
    """Test queries that must pass validation and generate sanitized SQL."""

    def test_simple_select(self):
        result = validate_sql("SELECT id, name, email FROM users")
        assert result.ok is True
        assert result.reason is None
        assert "users" in result.sanitized_sql.lower()
        assert result.limit_injected is True
        assert "limit 1000" in result.sanitized_sql.lower()

    def test_select_with_explicit_limit_under_threshold(self):
        result = validate_sql("SELECT * FROM products LIMIT 50")
        assert result.ok is True
        assert result.limit_injected is False
        assert "limit 50" in result.sanitized_sql.lower()

    def test_select_with_limit_over_threshold(self):
        result = validate_sql("SELECT * FROM products LIMIT 5000")
        assert result.ok is True
        assert result.limit_injected is True
        assert "limit 1000" in result.sanitized_sql.lower()

    def test_select_with_limit_all(self):
        result = validate_sql("SELECT * FROM products LIMIT ALL")
        assert result.ok is True
        assert result.limit_injected is True
        assert "limit 1000" in result.sanitized_sql.lower()

    def test_select_with_limit_null(self):
        result = validate_sql("SELECT * FROM products LIMIT NULL")
        assert result.ok is True
        assert result.limit_injected is True
        assert "limit 1000" in result.sanitized_sql.lower()

    def test_select_with_fetch_first(self):
        result = validate_sql("SELECT * FROM products FETCH FIRST 10 ROWS ONLY")
        assert result.ok is True
        assert result.limit_injected is False
        assert "fetch first 10 rows only" in result.sanitized_sql.lower()

    def test_select_with_fetch_first_clamped(self):
        result = validate_sql("SELECT * FROM products FETCH FIRST 5000 ROWS ONLY")
        assert result.ok is True
        assert result.limit_injected is True
        assert "fetch first 1000 rows only" in result.sanitized_sql.lower()

    def test_select_with_offset(self):
        result = validate_sql("SELECT * FROM users OFFSET 20")
        assert result.ok is True
        assert result.limit_injected is True
        assert "limit 1000" in result.sanitized_sql.lower()
        assert "offset 20" in result.sanitized_sql.lower()

    def test_aggregates_and_math(self):
        sql = "SELECT count(*), round(avg(price), 2), min(price), max(price) FROM products"
        result = validate_sql(sql)
        assert result.ok is True

    def test_string_and_date_functions(self):
        sql = """
        SELECT upper(name), length(email), date_trunc('month', created_at), to_char(created_at, 'YYYY-MM')
        FROM users
        WHERE email IS NOT NULL
        """
        result = validate_sql(sql)
        assert result.ok is True

    def test_case_expression(self):
        sql = "SELECT id, CASE WHEN stock > 0 THEN 'available' ELSE 'out_of_stock' END AS status FROM products"
        result = validate_sql(sql)
        assert result.ok is True

    def test_window_functions(self):
        sql = """
        SELECT id, user_id, total_amount,
               row_number() OVER (PARTITION BY user_id ORDER BY created_at DESC) as rn,
               rank() OVER (ORDER BY total_amount DESC) as rk
        FROM orders
        """
        result = validate_sql(sql)
        assert result.ok is True

    def test_joins_across_allowed_tables(self):
        sql = """
        SELECT o.id, u.email, oi.quantity, p.name, p.price
        FROM orders o
        JOIN users u ON o.user_id = u.id
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON oi.product_id = p.id
        WHERE o.status = 'delivered'
        """
        result = validate_sql(sql)
        assert result.ok is True

    def test_cte_query(self):
        sql = """
        WITH high_value_orders AS (
            SELECT id, user_id, total_amount FROM orders WHERE total_amount > 500
        )
        SELECT u.name, hvo.total_amount
        FROM high_value_orders hvo
        JOIN users u ON hvo.user_id = u.id
        """
        result = validate_sql(sql)
        assert result.ok is True

    def test_cte_shadowing_real_table_name(self):
        sql = "WITH users AS (SELECT 1 as id, 'mock' as name) SELECT * FROM users"
        result = validate_sql(sql)
        assert result.ok is True

    def test_subquery_in_from_clause(self):
        sql = "SELECT sub.id, sub.email FROM (SELECT id, email FROM users WHERE country = 'US') sub"
        result = validate_sql(sql)
        assert result.ok is True

    def test_lateral_join(self):
        sql = """
        SELECT u.id, u.name, o.id AS order_id
        FROM users u,
        LATERAL (SELECT id FROM orders WHERE orders.user_id = u.id LIMIT 1) o
        """
        result = validate_sql(sql)
        assert result.ok is True

    def test_tablesample(self):
        sql = "SELECT * FROM users TABLESAMPLE SYSTEM (10)"
        result = validate_sql(sql)
        assert result.ok is True

    def test_quoted_and_mixed_case_identifiers(self):
        result1 = validate_sql('SELECT * FROM "Users"')
        assert result1.ok is True

        result2 = validate_sql('SELECT * FROM public."users"')
        assert result2.ok is True

    def test_union_query(self):
        sql = "SELECT id, name FROM users UNION SELECT id, name FROM products"
        result = validate_sql(sql)
        assert result.ok is True
        assert "limit 1000" in result.sanitized_sql.lower()

    def test_sanitized_sql_revalidation_idempotent(self):
        sql = "SELECT id, email FROM users WHERE country = 'US' ORDER BY id DESC"
        first = validate_sql(sql)
        assert first.ok is True
        assert first.sanitized_sql is not None

        second = validate_sql(first.sanitized_sql)
        assert second.ok is True
        assert second.sanitized_sql == first.sanitized_sql
        assert second.limit_injected is False


class TestSqlValidatorRejectedQueries:
    """Test queries that must be blocked by the validator."""

    def test_empty_and_whitespace_input(self):
        assert validate_sql("").ok is False
        assert validate_sql("   ").ok is False
        assert validate_sql("\n\t").ok is False
        assert validate_sql(";").ok is False
        assert validate_sql(";;;").ok is False

    def test_max_length_exceeded(self):
        long_query = "SELECT * FROM users WHERE " + "id = 1 OR " * 2000 + "id = 1"
        res = validate_sql(long_query, max_length=500)
        assert res.ok is False
        assert "exceeds maximum allowed length" in res.reason

    def test_stacked_statements(self):
        res1 = validate_sql("SELECT 1; SELECT 2;")
        assert res1.ok is False
        assert "stacked queries" in res1.reason.lower()

        res2 = validate_sql("SELECT * FROM users; DROP TABLE users;")
        assert res2.ok is False

    def test_data_mutation_statements(self):
        mutations = [
            "INSERT INTO users (name, email, country) VALUES ('bad', 'bad@test.com', 'US')",
            "UPDATE users SET name = 'hacked'",
            "DELETE FROM orders",
            "DROP TABLE users",
            "ALTER TABLE users ADD COLUMN hacked text",
            "CREATE TABLE evil (id int)",
            "TRUNCATE users",
            "MERGE INTO users USING products ON users.id = products.id WHEN MATCHED THEN DELETE",
        ]
        for m in mutations:
            res = validate_sql(m)
            assert res.ok is False, f"Expected {m} to be rejected"

    def test_data_modifying_cte(self):
        sql = "WITH deleted AS (DELETE FROM orders RETURNING *) SELECT * FROM deleted"
        res = validate_sql(sql)
        assert res.ok is False
        assert "disallowed statement or command" in res.reason.lower()

    def test_select_into(self):
        sql = "SELECT * INTO stolen_users FROM users"
        res = validate_sql(sql)
        assert res.ok is False
        assert "into" in res.reason.lower()

    def test_locking_clauses(self):
        for lock in ["FOR UPDATE", "FOR SHARE", "FOR NO KEY UPDATE", "FOR KEY SHARE"]:
            sql = f"SELECT * FROM users {lock}"
            res = validate_sql(sql)
            assert res.ok is False, f"Expected {lock} to be rejected"
            assert "locking" in res.reason.lower()

    def test_prohibited_dangerous_functions(self):
        dangerous = [
            "SELECT pg_sleep(1)",
            "SELECT pg_catalog.pg_sleep(1)",
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT dblink('host=evil', 'SELECT 1')",
            "SELECT set_config('statement_timeout', '0', false)",
            "SELECT current_setting('statement_timeout')",
            "SELECT pg_terminate_backend(1)",
            "SELECT lo_import('/etc/passwd')",
        ]
        for q in dangerous:
            res = validate_sql(q)
            assert res.ok is False, f"Expected {q} to be rejected"
            assert "function" in res.reason.lower() or "not permitted" in res.reason.lower()

    def test_information_functions_and_pseudo_columns(self):
        info_queries = [
            "SELECT current_user",
            "SELECT session_user",
            "SELECT version()",
            "SELECT user",
        ]
        for q in info_queries:
            res = validate_sql(q)
            assert res.ok is False, f"Expected {q} to be rejected"
            assert "information" in res.reason.lower() or "not permitted" in res.reason.lower()

    def test_table_valued_functions_in_from(self):
        res1 = validate_sql("SELECT * FROM generate_series(1, 10)")
        assert res1.ok is False

        res2 = validate_sql("SELECT * FROM pg_read_file('test.txt')")
        assert res2.ok is False

    def test_unauthorized_tables(self):
        res1 = validate_sql("SELECT * FROM non_existent")
        assert res1.ok is False
        assert "not permitted" in res1.reason.lower()

        res2 = validate_sql("SELECT * FROM pg_catalog.pg_class")
        assert res2.ok is False

        res3 = validate_sql('SELECT * FROM "pg_catalog"."pg_class"')
        assert res3.ok is False

        res4 = validate_sql("SELECT * FROM information_schema.tables")
        assert res4.ok is False

    def test_unauthorized_schema(self):
        res = validate_sql("SELECT * FROM other_schema.users")
        assert res.ok is False
        assert "schema" in res.reason.lower()

    def test_non_literal_limits(self):
        res1 = validate_sql("SELECT * FROM users LIMIT (SELECT 5)")
        assert res1.ok is False
        assert "non-literal" in res1.reason.lower()

        res2 = validate_sql("SELECT * FROM users FETCH FIRST (SELECT 2) ROWS ONLY")
        assert res2.ok is False

    def test_negative_limit(self):
        res = validate_sql("SELECT * FROM users LIMIT -1")
        assert res.ok is False
        assert "negative" in res.reason.lower()

    def test_ddl_and_administrative_commands(self):
        admin_cmds = [
            "EXPLAIN SELECT * FROM users",
            "VACUUM users",
            "ANALYZE users",
            "SET statement_timeout = 0",
            "DISCARD ALL",
        ]
        for cmd in admin_cmds:
            res = validate_sql(cmd)
            assert res.ok is False, f"Expected {cmd} to be rejected"
