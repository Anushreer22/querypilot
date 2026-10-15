"""Direct database privilege escalation attack tests.

Verifies that even if an attacker bypasses application-level AST validation,
the database-level role permissions (readonly_user) strictly prevent all DDL,
DML, administration, and access to sensitive PostgreSQL system catalogs.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db.session import shop_engine


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation_sql", "description"),
    [
        ("INSERT INTO users (email, name) VALUES ('hacker@test.com', 'Hacker');", "INSERT"),
        ("UPDATE users SET name = 'Hacked' WHERE id = 1;", "UPDATE"),
        ("DELETE FROM users WHERE id = 1;", "DELETE"),
        ("TRUNCATE TABLE users;", "TRUNCATE"),
        ("DROP TABLE users;", "DROP TABLE"),
        ("CREATE INDEX idx_test_attack ON users(email);", "CREATE INDEX"),
        ("CREATE TABLE test_attack_table (id int);", "CREATE TABLE"),
        ("COPY users TO PROGRAM 'echo hacked';", "COPY TO PROGRAM"),
    ],
)
async def test_readonly_user_database_level_mutations_blocked(
    mutation_sql: str, description: str
) -> None:
    """Postgres readonly_user role must reject all data-modifying and DDL statements directly."""
    with pytest.raises((DBAPIError, ProgrammingError)) as exc_info:
        async with shop_engine.connect() as conn:
            await conn.execute(text(mutation_sql))
            await conn.commit()

    err_msg = str(exc_info.value).lower()
    # Postgres error messages: permission denied, read-only transaction, or must be superuser
    assert any(
        kw in err_msg
        for kw in (
            "permission denied",
            "must be superuser",
            "must be owner",
            "read-only",
            "insufficientprivilege",
        )
    ), f"Expected privilege rejection for {description}, got: {err_msg}"


@pytest.mark.asyncio
async def test_readonly_user_cannot_read_pg_authid() -> None:
    """Postgres readonly_user role must not have SELECT privileges on pg_authid (password hashes)."""
    with pytest.raises((DBAPIError, ProgrammingError)) as exc_info:
        async with shop_engine.connect() as conn:
            await conn.execute(text("SELECT * FROM pg_authid;"))

    err_msg = str(exc_info.value).lower()
    assert "permission denied" in err_msg or "insufficientprivilege" in err_msg
