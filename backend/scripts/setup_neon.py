#!/usr/bin/env python3
"""Automated One-Click Setup Script for Neon Serverless PostgreSQL.

This script takes a base Neon connection string (from neon.tech) and automatically:
1. Connects to the Neon compute endpoint (direct compute, stripping -pooler for DDL)
2. Creates the two required logical databases: 'querypilot_app' and 'sample_shop'
3. Creates the hardened security roles: 'app_rw' and 'readonly_user' with secure passwords
4. Applies all role-level constraints (default_transaction_read_only=on, statement_timeout=5s)
5. Applies all schema grants and permissions
6. Executes Alembic migrations for querypilot_app
7. Executes Alembic migrations for sample_shop
8. Seeds sample_shop with the --medium dataset (~65 MB, perfectly within Neon's 500 MB free cap)
9. Performs end-to-end verification (read-only enforcement, table counts)
10. Outputs the exact environment variables ready to copy into Render and Vercel!

Usage:
    python backend/scripts/setup_neon.py --connection-string "postgresql://neondb_owner:***@ep-xyz.neon.tech/neondb?sslmode=require"
"""

import argparse
import os
import secrets
import string
import subprocess
import sys
import time
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse, urlunparse

import psycopg
from psycopg import sql

# Add backend directory to sys.path so we can import app modules if needed
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def generate_password(length: int = 40) -> str:
    """Generate a cryptographically secure password meeting Neon control plane requirements."""
    alphabet = string.ascii_letters + string.digits + "_-"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "_-" for c in pwd)
        ):
            return pwd


def normalize_neon_url(
    raw_url: str,
    target_db: str | None = None,
    role: str | None = None,
    password: str | None = None,
    direct: bool = True,
) -> tuple[str, str]:
    """Parse and normalize Neon connection URL.

    Args:
        raw_url: The input connection URL.
        target_db: Logical database name to connect to.
        role: Username/role to connect as.
        password: Password for the role.
        direct: If True, strips '-pooler' to connect directly to the compute endpoint.

    Returns:
        (raw_psycopg_url, async_sqlalchemy_url)
    """
    clean_url = raw_url.strip().strip("'\"")
    clean_url = clean_url.replace("postgresql+psycopg://", "postgresql://")
    if clean_url.startswith("postgres://"):
        clean_url = "postgresql://" + clean_url[len("postgres://") :]

    parsed = urlparse(clean_url)
    if not parsed.hostname:
        raise ValueError(
            f"Invalid database connection URL: unable to extract hostname from '{raw_url}'"
        )

    hostname = parsed.hostname
    if direct and hostname:
        hostname = hostname.replace("-pooler", "")

    user = role if role else parsed.username
    pwd = password if password else parsed.password
    db = target_db if target_db else (parsed.path.lstrip("/") or "neondb")

    query_params = parse_qs(parsed.query)
    # Ensure sslmode=require
    query_params["sslmode"] = ["require"]
    new_query = urlencode(query_params, doseq=True)

    # Safely percent-encode password for URL insertion
    encoded_pwd = quote_plus(pwd, safe="") if pwd else ""
    auth = f"{user}:{encoded_pwd}@" if user and encoded_pwd else (f"{user}@" if user else "")
    port_part = f":{parsed.port}" if parsed.port else ""
    netloc = f"{auth}{hostname}{port_part}"

    raw_psycopg_url = urlunparse(("postgresql", netloc, f"/{db}", "", new_query, ""))
    async_sa_url = urlunparse(("postgresql+psycopg", netloc, f"/{db}", "", new_query, ""))

    return raw_psycopg_url, async_sa_url


def log_step(step_num: int, total_steps: int, title: str) -> None:
    print(f"\n[{step_num}/{total_steps}] {title}...")


def setup_neon(
    base_url: str,
    app_rw_pass: str | None = None,
    readonly_pass: str | None = None,
    skip_seed: bool = False,
    scale: str = "medium",
) -> dict[str, str]:
    start_time = time.time()
    total_steps = 7 if not skip_seed else 6
    app_rw_password = app_rw_pass or generate_password(32)
    readonly_password = readonly_pass or generate_password(32)

    print("=" * 70)
    print(" QueryPilot Neon Serverless PostgreSQL Automated Provisioning")
    print("=" * 70)

    # 1. Connect to base DB as admin
    log_step(1, total_steps, "Connecting to Neon compute endpoint as admin")
    admin_conn_str, _ = normalize_neon_url(base_url)

    try:
        with psycopg.connect(admin_conn_str, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("SELECT version();")
            ver = cur.fetchone()[0]
            print(f"   Connected to PostgreSQL: {ver.split(',')[0]}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERROR] Failed to connect to Neon with provided connection string:\n{exc}")
        print(
            "\nPlease check that your Neon project is active and the connection string is correct."
        )
        sys.exit(1)

    # 2. Create logical databases and roles
    log_step(
        2, total_steps, "Configuring logical databases ('querypilot_app', 'sample_shop') & roles"
    )
    with psycopg.connect(admin_conn_str, autocommit=True) as conn, conn.cursor() as cur:
        # Create databases if they don't exist
        for db_name in ["querypilot_app", "sample_shop"]:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
            if cur.fetchone():
                print(f"   Database '{db_name}' already exists.")
            else:
                cur.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(db_name)))
                print(f"   Created database '{db_name}'.")

        # Create or update app_rw role
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'app_rw';")
        if not cur.fetchone():
            cur.execute(
                sql.SQL("CREATE ROLE app_rw WITH LOGIN PASSWORD {pwd};").format(
                    pwd=sql.Literal(app_rw_password)
                )
            )
            print("   Created role 'app_rw'.")
        else:
            cur.execute(
                sql.SQL("ALTER ROLE app_rw WITH PASSWORD {pwd};").format(
                    pwd=sql.Literal(app_rw_password)
                )
            )
            print("   Updated password for existing role 'app_rw'.")

        # Create or update readonly_user role
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'readonly_user';")
        if not cur.fetchone():
            cur.execute(
                sql.SQL("CREATE ROLE readonly_user WITH LOGIN PASSWORD {pwd};").format(
                    pwd=sql.Literal(readonly_password)
                )
            )
            print("   Created role 'readonly_user'.")
        else:
            cur.execute(
                sql.SQL("ALTER ROLE readonly_user WITH PASSWORD {pwd};").format(
                    pwd=sql.Literal(readonly_password)
                )
            )
            print("   Updated password for existing role 'readonly_user'.")

        # Role security defaults
        cur.execute("ALTER ROLE readonly_user SET default_transaction_read_only = on;")
        cur.execute("ALTER ROLE readonly_user SET statement_timeout = '5s';")
        cur.execute("ALTER ROLE readonly_user CONNECTION LIMIT 20;")
        cur.execute("ALTER ROLE app_rw SET statement_timeout = '15s';")
        print("   Applied role-level constraints (read-only default=on, 5s timeout).")

        # DB level connect grants
        cur.execute('REVOKE CONNECT ON DATABASE "querypilot_app" FROM PUBLIC;')
        cur.execute('GRANT CONNECT ON DATABASE "querypilot_app" TO app_rw;')
        cur.execute('GRANT ALL PRIVILEGES ON DATABASE "querypilot_app" TO app_rw;')

        cur.execute('REVOKE ALL ON DATABASE "sample_shop" FROM readonly_user;')
        cur.execute('GRANT CONNECT ON DATABASE "sample_shop" TO readonly_user;')
        print("   Configured database-level connection privileges.")

    # 3. Configure permissions inside querypilot_app
    log_step(3, total_steps, "Configuring schema permissions in 'querypilot_app'")
    app_admin_conn, _ = normalize_neon_url(base_url, target_db="querypilot_app")
    with psycopg.connect(app_admin_conn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("GRANT ALL ON SCHEMA public TO app_rw;")
        cur.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_rw;")
        cur.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_rw;")
        cur.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_rw;")
        cur.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO app_rw;")
        print("   Granted schema ownership & default DML privileges to 'app_rw'.")

    # 4. Configure permissions inside sample_shop
    log_step(4, total_steps, "Configuring read-only permissions in 'sample_shop'")
    shop_admin_conn, _ = normalize_neon_url(base_url, target_db="sample_shop")
    with psycopg.connect(shop_admin_conn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC;")
        cur.execute("REVOKE CREATE ON SCHEMA public FROM readonly_user;")
        cur.execute("GRANT USAGE ON SCHEMA public TO readonly_user;")
        cur.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;"
        )
        cur.execute(
            "REVOKE EXECUTE ON FUNCTION pg_sleep(double precision) FROM PUBLIC, readonly_user;"
        )
        print("   Configured read-only defaults and revoked pg_sleep for 'readonly_user'.")

    # 5. Run Alembic migrations
    log_step(5, total_steps, "Executing Alembic schema migrations on Neon")

    # App uses app_rw role
    _, app_sa_url = normalize_neon_url(
        base_url, target_db="querypilot_app", role="app_rw", password=app_rw_password
    )
    # Shop admin uses admin role for DDL
    _, shop_admin_sa_url = normalize_neon_url(base_url, target_db="sample_shop")

    env_alembic = os.environ.copy()
    env_alembic["APP_DATABASE_URL"] = app_sa_url
    env_alembic["SHOP_ADMIN_DATABASE_URL"] = shop_admin_sa_url

    print("   - Running querypilot_app migrations (alembic.ini)...")
    res1 = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            os.path.join(BACKEND_DIR, "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=BACKEND_DIR,
        env=env_alembic,
        capture_output=True,
        text=True,
        check=False,
    )
    if res1.returncode != 0:
        print(f"[ERROR] querypilot_app migration failed:\n{res1.stderr}")
        sys.exit(1)
    print("     querypilot_app schema migrated successfully.")

    print("   - Running sample_shop migrations (alembic_shop.ini)...")
    res2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            os.path.join(BACKEND_DIR, "alembic_shop.ini"),
            "upgrade",
            "head",
        ],
        cwd=BACKEND_DIR,
        env=env_alembic,
        capture_output=True,
        text=True,
        check=False,
    )
    if res2.returncode != 0:
        print(f"[ERROR] sample_shop migration failed:\n{res2.stderr}")
        sys.exit(1)
    print("     sample_shop schema migrated successfully.")

    # Grant SELECT on all created tables to readonly_user
    with psycopg.connect(shop_admin_conn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;")
        print("     Verified SELECT grant on all created tables for 'readonly_user'.")

    # 6. Seed sample_shop
    if not skip_seed:
        log_step(
            6,
            total_steps,
            f"Seeding sample_shop with {scale.upper()} dataset",
        )
        from scripts.seed_shop import seed_sample_shop

        seed_sample_shop(
            database_url=shop_admin_conn,
            medium=(scale == "medium"),
            small=(scale == "small"),
            reset=True,
        )
    else:
        print("\n[6/7] Seeding skipped (--skip-seed specified).")

    # 7. Verification & Sanity Checks
    log_step(total_steps, total_steps, "Running End-to-End Verification against Neon")
    app_rw_conn, _ = normalize_neon_url(
        base_url, target_db="querypilot_app", role="app_rw", password=app_rw_password
    )
    shop_ro_conn, shop_ro_sa_url = normalize_neon_url(
        base_url, target_db="sample_shop", role="readonly_user", password=readonly_password
    )

    # Verify querypilot_app
    with psycopg.connect(app_rw_conn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
        table_count = cur.fetchone()[0]
        print(f"   [PASS] querypilot_app accessible via 'app_rw': {table_count} tables verified.")

    # Verify sample_shop
    with psycopg.connect(shop_ro_conn) as conn, conn.cursor() as cur:
        cur.execute("SELECT current_setting('default_transaction_read_only');")
        ro_setting = cur.fetchone()[0]
        if ro_setting != "on":
            raise RuntimeError(
                f"FATAL: readonly_user default_transaction_read_only is '{ro_setting}', expected 'on'"
            )
        print("   [PASS] sample_shop readonly_user default_transaction_read_only is strictly 'on'.")

        cur.execute("SELECT count(*) FROM products;")
        prod_count = cur.fetchone()[0]
        print(f"   [PASS] sample_shop products table verified: {prod_count:,} products readable.")

        # Test write rejection
        try:
            cur.execute("CREATE TABLE test_should_fail (id int);")
            raise AssertionError(
                "CRITICAL SECURITY FAILED: readonly_user was able to create a table!"
            )
        except psycopg.errors.ReadOnlySqlTransaction:
            print("   [PASS] sample_shop write rejection verified (ReadOnlySqlTransaction).")
        except psycopg.Error:
            print("   [PASS] sample_shop write rejected as expected.")

    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print(f" Neon Setup Completed Successfully in {total_time:.1f}s!")
    print("=" * 70)

    print("\n COPY-PASTE THESE VARIABLES INTO RENDER (or your .env.production):\n")
    print(f"APP_DATABASE_URL={app_sa_url}")
    print(f"SHOP_DATABASE_URL={shop_ro_sa_url}")
    print("\n" + "-" * 70)
    print("Admin Connection Strings (keep safe for future migrations):")
    print(f"SHOP_ADMIN_DATABASE_URL={shop_admin_sa_url}")
    print("=" * 70 + "\n")

    return {
        "APP_DATABASE_URL": app_sa_url,
        "SHOP_DATABASE_URL": shop_ro_sa_url,
        "SHOP_ADMIN_DATABASE_URL": shop_admin_sa_url,
    }


def main():
    parser = argparse.ArgumentParser(
        description="One-click automated setup for Neon Serverless PostgreSQL."
    )
    parser.add_argument(
        "--connection-string",
        "-c",
        required=True,
        help="Base admin connection string copied from Neon dashboard (e.g. postgresql://neondb_owner:***@ep-xyz.neon.tech/neondb?sslmode=require)",
    )
    parser.add_argument(
        "--app-rw-password",
        default=None,
        help="Custom password for app_rw role (optional, auto-generated if omitted)",
    )
    parser.add_argument(
        "--readonly-password",
        default=None,
        help="Custom password for readonly_user role (optional, auto-generated if omitted)",
    )
    parser.add_argument(
        "--scale",
        choices=["small", "medium"],
        default="medium",
        help="Dataset scale for sample_shop: 'medium' (~65MB, recommended) or 'small' (~5MB)",
    )
    parser.add_argument(
        "--skip-seed", action="store_true", help="Skip seeding initial sample_shop data"
    )

    args = parser.parse_args()
    setup_neon(
        base_url=args.connection_string,
        app_rw_pass=args.app_rw_password,
        readonly_pass=args.readonly_password,
        skip_seed=args.skip_seed,
        scale=args.scale,
    )


if __name__ == "__main__":
    main()
