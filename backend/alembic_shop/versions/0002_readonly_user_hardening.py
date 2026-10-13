"""Harden readonly_user with role-level defaults and connection limits

Revision ID: 0002_readonly_hardening
Revises: 0001_sample_shop
Create Date: 2026-10-13 07:10:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_readonly_hardening"
down_revision: str | None = "0001_sample_shop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Defense in depth: role-level safeguards for readonly_user
    op.execute("ALTER ROLE readonly_user SET default_transaction_read_only = on;")
    op.execute("ALTER ROLE readonly_user SET statement_timeout = '5s';")
    op.execute("ALTER ROLE readonly_user CONNECTION LIMIT 20;")
    op.execute("REVOKE EXECUTE ON FUNCTION pg_sleep(double precision) FROM PUBLIC, readonly_user;")


def downgrade() -> None:
    op.execute("GRANT EXECUTE ON FUNCTION pg_sleep(double precision) TO PUBLIC;")
    op.execute("ALTER ROLE readonly_user RESET default_transaction_read_only;")
    op.execute("ALTER ROLE readonly_user RESET statement_timeout;")
    op.execute("ALTER ROLE readonly_user CONNECTION LIMIT -1;")
