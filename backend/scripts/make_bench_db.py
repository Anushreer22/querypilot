"""Script to create or reset the isolated sample_shop_bench database using PostgreSQL TEMPLATE cloning."""

import argparse
import logging
import sys
from urllib.parse import urlparse

import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def create_or_reset_bench_db(
    admin_url: str = "postgresql://postgres:querypilot_postgres_pass@127.0.0.1:5436/postgres",
) -> bool:
    """Create or reset sample_shop_bench database as an exact clone of sample_shop."""
    parsed = urlparse(admin_url)
    # Ensure connecting to 'postgres' maintenance database for administrative DDL
    maintenance_url = (
        f"postgresql://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}/postgres"
    )

    logger.info("Connecting to maintenance database to configure sample_shop_bench...")
    try:
        with (
            psycopg.connect(maintenance_url, autocommit=True) as conn,
            conn.cursor() as cur,
        ):
            # 1. Terminate existing connections to allow template cloning
            logger.info("Terminating active connections on sample_shop and sample_shop_bench...")
            cur.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname IN ('sample_shop', 'sample_shop_bench')
                  AND pid <> pg_backend_pid();
                """
            )

            # 2. Drop existing benchmark database if present
            logger.info("Dropping existing sample_shop_bench if it exists...")
            cur.execute("DROP DATABASE IF EXISTS sample_shop_bench WITH (FORCE);")

            # 3. Clone sample_shop via TEMPLATE
            logger.info("Cloning sample_shop into sample_shop_bench using TEMPLATE...")
            cur.execute("CREATE DATABASE sample_shop_bench WITH TEMPLATE sample_shop;")

            logger.info("sample_shop_bench successfully cloned and initialized.")
            return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to clone sample_shop_bench: %s", exc)
        return False


def check_bench_db(
    admin_url: str = "postgresql://postgres:querypilot_postgres_pass@127.0.0.1:5436/postgres",
) -> bool:
    """Check if sample_shop_bench exists and is accessible."""
    parsed = urlparse(admin_url)
    bench_url = f"postgresql://readonly_user:querypilot_readonly_pass@{parsed.hostname}:{parsed.port}/sample_shop_bench"
    try:
        with psycopg.connect(bench_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM users;")
            count = cur.fetchone()[0]
            logger.info("sample_shop_bench is online with %d users.", count)
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("sample_shop_bench check failed: %s", exc)
        return False


def main():
    parser = argparse.ArgumentParser(description="Manage QueryPilot benchmark database.")
    parser.add_argument(
        "--check", action="store_true", help="Check if benchmark database exists and is valid."
    )
    parser.add_argument(
        "--reset", action="store_true", help="Force clone/reset benchmark database."
    )
    args = parser.parse_args()

    if args.check:
        success = check_bench_db()
        sys.exit(0 if success else 1)

    success = create_or_reset_bench_db()
    if success:
        check_bench_db()
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
