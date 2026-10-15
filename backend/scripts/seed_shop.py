#!/usr/bin/env python3
"""High-performance seed script for sample_shop e-commerce database.

Generates realistic data with:
- ~50k users (or 1k with --small)
- ~5k products (or 200 with --small)
- ~500k orders (or 5k with --small)
- ~1.5M order_items (or ~15k with --small)
- Dates spread over the last 2 years (730 days) with Q4 seasonal holiday peaks
- Realistic power-user (Pareto/Zipf) and product-popularity distributions
- Order total_amount strictly matching sum of line items for 100% of orders
- Fast batch ingestion using PostgreSQL COPY via psycopg 3
- Safety check: refuses to execute against any database other than 'sample_shop'
"""

import argparse
import io
import os
import sys
import time
from datetime import UTC, datetime, timedelta

import numpy as np
import psycopg

# Target scales
FULL_USERS = 50_000
FULL_PRODUCTS = 5_000
FULL_ORDERS = 500_000

MEDIUM_USERS = 10_000
MEDIUM_PRODUCTS = 1_000
MEDIUM_ORDERS = 100_000

SMALL_USERS = 1_000
SMALL_PRODUCTS = 200
SMALL_ORDERS = 5_000

# Name pools for fast in-memory combination
FIRST_NAMES = [
    "James",
    "Mary",
    "John",
    "Patricia",
    "Robert",
    "Jennifer",
    "Michael",
    "Linda",
    "William",
    "Elizabeth",
    "David",
    "Barbara",
    "Richard",
    "Susan",
    "Joseph",
    "Jessica",
    "Thomas",
    "Sarah",
    "Charles",
    "Karen",
    "Christopher",
    "Nancy",
    "Daniel",
    "Lisa",
    "Matthew",
    "Betty",
    "Anthony",
    "Margaret",
    "Mark",
    "Sandra",
    "Donald",
    "Ashley",
    "Steven",
    "Kimberly",
    "Paul",
    "Emily",
    "Andrew",
    "Donna",
    "Joshua",
    "Michelle",
    "Kenneth",
    "Carol",
    "Kevin",
    "Amanda",
    "Brian",
    "Melissa",
    "George",
    "Deborah",
    "Edward",
    "Stephanie",
    "Ronald",
    "Rebecca",
    "Timothy",
    "Sharon",
    "Jason",
    "Laura",
    "Jeffrey",
    "Cynthia",
    "Ryan",
    "Amy",
    "Jacob",
    "Kathleen",
    "Gary",
    "Angela",
    "Nicholas",
    "Shirley",
    "Eric",
    "Emma",
    "Jonathan",
    "Brenda",
    "Stephen",
    "Pamela",
    "Larry",
    "Nicole",
    "Justin",
    "Anna",
    "Scott",
    "Samantha",
    "Brandon",
    "Katherine",
]

LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
    "Lee",
    "Perez",
    "Thompson",
    "White",
    "Harris",
    "Sanchez",
    "Clark",
    "Ramirez",
    "Lewis",
    "Robinson",
    "Walker",
    "Young",
    "Allen",
    "King",
    "Wright",
    "Scott",
    "Torres",
    "Nguyen",
    "Hill",
    "Flores",
    "Green",
    "Adams",
    "Nelson",
    "Baker",
    "Hall",
    "Rivera",
    "Campbell",
    "Mitchell",
    "Carter",
    "Roberts",
    "Gomez",
    "Phillips",
    "Evans",
    "Turner",
    "Diaz",
    "Parker",
    "Cruz",
    "Edwards",
    "Collins",
    "Reyes",
    "Stewart",
    "Morris",
    "Morales",
    "Murphy",
    "Cook",
    "Rogers",
    "Gutierrez",
    "Ortiz",
    "Morgan",
    "Cooper",
    "Peterson",
    "Bailey",
]

COUNTRIES = [
    "United States",
    "United Kingdom",
    "Germany",
    "Canada",
    "France",
    "India",
    "Australia",
    "Japan",
    "Brazil",
    "Netherlands",
]
COUNTRY_WEIGHTS = [0.40, 0.12, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.04, 0.04]

CATEGORIES = [
    "Electronics",
    "Apparel",
    "Home & Kitchen",
    "Books",
    "Health & Beauty",
    "Sports & Outdoors",
    "Toys & Games",
    "Automotive",
]

PRODUCT_ADJECTIVES = [
    "Ultra",
    "Pro",
    "Smart",
    "Eco",
    "Classic",
    "Premium",
    "Compact",
    "Wireless",
    "Ergonomic",
    "Portable",
    "Digital",
    "Precision",
    "Heavy-Duty",
    "Modern",
    "Vintage",
]

PRODUCT_NOUNS = [
    "Headphones",
    "T-Shirt",
    "Coffee Maker",
    "Backpack",
    "Fitness Tracker",
    "LED Desk Lamp",
    "Water Bottle",
    "Running Shoes",
    "Wireless Mouse",
    "Keyboard",
    "Blender",
    "Cookware Set",
    "Smartphone Case",
    "Yoga Mat",
    "Bluetooth Speaker",
    "Novel",
    "Notebook",
    "Desk Chair",
    "Power Bank",
    "Air Purifier",
]

ORDER_STATUSES = ["delivered", "shipped", "paid", "pending", "cancelled", "refunded"]
STATUS_WEIGHTS = [0.72, 0.10, 0.06, 0.04, 0.05, 0.03]


def get_default_database_url() -> str:
    """Read privileged database URL from environment or fallback to Docker container default."""
    from app.core.config import settings

    return settings.shop_admin_database_url


def seed_sample_shop(
    database_url: str,
    seed: int = 42,
    small: bool = False,
    medium: bool = False,
    reset: bool = True,
) -> None:
    start_total_time = time.time()
    rng = np.random.default_rng(seed)

    if small:
        num_users = SMALL_USERS
        num_products = SMALL_PRODUCTS
        num_orders = SMALL_ORDERS
    elif medium:
        num_users = MEDIUM_USERS
        num_products = MEDIUM_PRODUCTS
        num_orders = MEDIUM_ORDERS
    else:
        num_users = FULL_USERS
        num_products = FULL_PRODUCTS
        num_orders = FULL_ORDERS

    print("=== Starting sample_shop Seed ===")
    mode_str = "SMALL (--small)" if small else ("MEDIUM (--medium)" if medium else "FULL")
    print(f"Mode: {mode_str}")
    print(f"Random seed: {seed}")
    print(f"Target: {num_users:,} users, {num_products:,} products, ~{num_orders:,} orders")

    # Connect to PostgreSQL
    # If URL starts with postgresql+psycopg://, strip driver for psycopg.connect()
    raw_url = database_url.replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(raw_url, autocommit=False)

    try:
        cur = conn.cursor()

        # 1. SAFETY CHECK: Must only ever run against sample_shop or sample_shop_bench
        cur.execute("SELECT current_database();")
        active_db = cur.fetchone()[0]
        if active_db not in ("sample_shop", "sample_shop_bench"):
            raise ValueError(
                f"SAFETY CHECK FAILED: seed script is restricted to database 'sample_shop' or 'sample_shop_bench', but connected to '{active_db}'!"
            )

        # 2. Reset if requested
        if reset:
            print("Resetting tables (TRUNCATE RESTART IDENTITY CASCADE)...")
            t0 = time.time()
            cur.execute(
                "TRUNCATE TABLE order_items, orders, products, users RESTART IDENTITY CASCADE;"
            )
            conn.commit()
            print(f"Reset completed in {time.time() - t0:.2f}s")

        now = datetime.now(UTC)
        start_date = now - timedelta(days=730)

        # ---------------------------------------------------------
        # 3. Generate & Ingest Users
        # ---------------------------------------------------------
        print(f"Generating {num_users:,} users...")
        t0 = time.time()

        user_first_idx = rng.integers(0, len(FIRST_NAMES), size=num_users)
        user_last_idx = rng.integers(0, len(LAST_NAMES), size=num_users)
        user_country_idx = rng.choice(len(COUNTRIES), size=num_users, p=COUNTRY_WEIGHTS)
        # Uniform user creation dates over past 730 days
        user_created_offsets = rng.uniform(0, 720 * 86400, size=num_users)
        user_created_dates = [
            start_date + timedelta(seconds=float(off)) for off in user_created_offsets
        ]

        # Ingest users with COPY
        user_buf = io.StringIO()
        for i in range(num_users):
            uid = i + 1
            fn = FIRST_NAMES[user_first_idx[i]]
            ln = LAST_NAMES[user_last_idx[i]]
            name = f"{fn} {ln}"
            email = f"{fn.lower()}.{ln.lower()}.{uid}@example.com"
            country = COUNTRIES[user_country_idx[i]]
            created_str = user_created_dates[i].strftime("%Y-%m-%d %H:%M:%S%z")
            user_buf.write(f"{uid}\t{name}\t{email}\t{country}\t{created_str}\n")

        user_buf.seek(0)
        with cur.copy("COPY users (id, name, email, country, created_at) FROM STDIN") as copy:
            copy.write(user_buf.getvalue())
        conn.commit()
        print(f"Ingested {num_users:,} users in {time.time() - t0:.2f}s")

        # ---------------------------------------------------------
        # 4. Generate & Ingest Products
        # ---------------------------------------------------------
        print(f"Generating {num_products:,} products...")
        t0 = time.time()

        product_prices = []
        product_buf = io.StringIO()
        for pid in range(1, num_products + 1):
            cat = CATEGORIES[(pid - 1) % len(CATEGORIES)]
            adj = PRODUCT_ADJECTIVES[rng.integers(0, len(PRODUCT_ADJECTIVES))]
            noun = PRODUCT_NOUNS[rng.integers(0, len(PRODUCT_NOUNS))]
            pname = f"{adj} {noun} #{pid}"
            # Prices vary by category
            base_price = rng.uniform(5.0, 500.0)
            if cat == "Electronics":
                base_price = rng.uniform(25.0, 1200.0)
            elif cat == "Books":
                base_price = rng.uniform(4.99, 45.0)
            price = round(float(base_price), 2)
            product_prices.append(price)
            stock = int(rng.integers(0, 500))
            p_created = (start_date + timedelta(days=int(rng.integers(0, 30)))).strftime(
                "%Y-%m-%d %H:%M:%S%z"
            )
            product_buf.write(f"{pid}\t{pname}\t{cat}\t{price:.2f}\t{stock}\t{p_created}\n")

        product_buf.seek(0)
        with cur.copy(
            "COPY products (id, name, category, price, stock, created_at) FROM STDIN"
        ) as copy:
            copy.write(product_buf.getvalue())
        conn.commit()
        print(f"Ingested {num_products:,} products in {time.time() - t0:.2f}s")

        # ---------------------------------------------------------
        # 5. Generate & Ingest Orders and Order Items
        # ---------------------------------------------------------
        print(
            f"Generating and streaming ~{num_orders:,} orders and ~{num_orders * 3:,} order_items..."
        )
        t0 = time.time()

        # Power law distribution for user order frequency (Pareto):
        # Top 10% of users place ~50% of the orders
        user_assignments = (rng.power(0.35, size=num_orders) * num_users).astype(np.int64) + 1
        user_assignments = np.clip(user_assignments, 1, num_users)

        # Status distribution
        order_status_choices = rng.choice(len(ORDER_STATUSES), size=num_orders, p=STATUS_WEIGHTS)

        # Seasonal order volume: Nov/Dec (days 300-365 and 665-730) have higher weight
        days_range = np.arange(725)
        day_weights = np.ones(725)
        # Nov & Dec boost
        for d in days_range:
            day_of_year = d % 365
            if 305 <= day_of_year <= 360:  # November / December
                day_weights[d] = 2.6
            elif 180 <= day_of_year <= 210:  # July summer sale
                day_weights[d] = 1.4
        day_weights /= day_weights.sum()
        order_day_offsets = rng.choice(725, size=num_orders, p=day_weights)

        # Product popularity: Zipfian / power-law distribution
        item_product_choices = (rng.power(0.40, size=num_orders * 5) * num_products).astype(
            np.int64
        ) + 1
        item_product_choices = np.clip(item_product_choices, 1, num_products)

        # Batch streaming to maintain low memory footprint while maximizing psycopg COPY speed
        BATCH_SIZE = 50_000
        order_item_id = 1
        total_items_count = 0
        prod_ptr = 0

        for batch_start in range(0, num_orders, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, num_orders)

            orders_buf = io.StringIO()
            items_buf = io.StringIO()

            for i in range(batch_start, batch_end):
                oid = i + 1
                uid = int(user_assignments[i])
                u_created = user_created_dates[uid - 1]

                # Order must be created after user account creation
                o_offset_days = int(order_day_offsets[i])
                o_time = start_date + timedelta(
                    days=o_offset_days, seconds=float(rng.uniform(0, 86400))
                )
                if o_time < u_created:
                    o_time = u_created + timedelta(hours=float(rng.uniform(1, 48)))

                status = ORDER_STATUSES[order_status_choices[i]]

                # Each order has 1 to 5 items (avg ~3)
                num_items_in_order = int(
                    rng.choice([1, 2, 3, 4, 5], p=[0.30, 0.35, 0.20, 0.10, 0.05])
                )
                order_total = 0.0

                for _ in range(num_items_in_order):
                    pid = int(item_product_choices[prod_ptr % len(item_product_choices)])
                    prod_ptr += 1

                    qty = int(rng.choice([1, 2, 3, 4], p=[0.72, 0.20, 0.06, 0.02]))
                    unit_price = product_prices[pid - 1]
                    order_total += qty * unit_price

                    items_buf.write(f"{order_item_id}\t{oid}\t{pid}\t{qty}\t{unit_price:.2f}\n")
                    order_item_id += 1
                    total_items_count += 1

                order_total = round(order_total, 2)
                o_date_str = o_time.strftime("%Y-%m-%d %H:%M:%S%z")
                orders_buf.write(f"{oid}\t{uid}\t{status}\t{order_total:.2f}\t{o_date_str}\n")

            # Stream batch via COPY
            orders_buf.seek(0)
            with cur.copy(
                "COPY orders (id, user_id, status, total_amount, created_at) FROM STDIN"
            ) as copy:
                copy.write(orders_buf.getvalue())

            items_buf.seek(0)
            with cur.copy(
                "COPY order_items (id, order_id, product_id, quantity, unit_price) FROM STDIN"
            ) as copy:
                copy.write(items_buf.getvalue())

            conn.commit()
            print(
                f"  Ingested orders {batch_start + 1:,} to {batch_end:,} ({total_items_count:,} total items)..."
            )

        print(
            f"Ingested {num_orders:,} orders and {total_items_count:,} order_items in {time.time() - t0:.2f}s"
        )

        # ---------------------------------------------------------
        # 6. Synchronize Identity Sequences
        # ---------------------------------------------------------
        print("Synchronizing sequence counters...")
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT COALESCE(MAX(id), 1) FROM users));"
        )
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('products', 'id'), (SELECT COALESCE(MAX(id), 1) FROM products));"
        )
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('orders', 'id'), (SELECT COALESCE(MAX(id), 1) FROM orders));"
        )
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('order_items', 'id'), (SELECT COALESCE(MAX(id), 1) FROM order_items));"
        )
        conn.commit()

        # ---------------------------------------------------------
        # 7. Run ANALYZE for query planner statistics
        # ---------------------------------------------------------
        print("Running ANALYZE on sample_shop tables...")
        t0 = time.time()
        cur.execute("ANALYZE users, products, orders, order_items;")
        conn.commit()
        print(f"ANALYZE completed in {time.time() - t0:.2f}s")

        # ---------------------------------------------------------
        # 8. Exact Verification: total_amount equals sum of line items for ALL orders
        # ---------------------------------------------------------
        print(
            "Verifying integrity: validating total_amount == sum(quantity * unit_price) for ALL orders..."
        )
        t0 = time.time()
        cur.execute("""
            SELECT count(*)
            FROM orders o
            LEFT JOIN (
                SELECT order_id, SUM(quantity * unit_price) AS items_sum
                FROM order_items
                GROUP BY order_id
            ) i ON o.id = i.order_id
            WHERE ABS(o.total_amount - COALESCE(i.items_sum, 0)) > 0.001;
        """)
        mismatched_orders = cur.fetchone()[0]
        if mismatched_orders > 0:
            raise AssertionError(
                f"DATA INTEGRITY ERROR: Found {mismatched_orders} orders with total_amount mismatch!"
            )
        print(
            f"Integrity check passed: 100% of orders ({num_orders:,}) match line items sum in {time.time() - t0:.2f}s"
        )

        # ---------------------------------------------------------
        # 9. Summary & Final Counts
        # ---------------------------------------------------------
        cur.execute("SELECT count(*) FROM users;")
        final_users = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM products;")
        final_products = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM orders;")
        final_orders = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM order_items;")
        final_items = cur.fetchone()[0]

        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()));")
        db_size_res = cur.fetchone()
        db_size = db_size_res[0] if db_size_res else "unknown"

        total_elapsed = time.time() - start_total_time
        print("\n=== Seeding Summary ===")
        print(f"Database:      {active_db}")
        print(f"Database Size: {db_size}")
        print(f"Users:         {final_users:,}")
        print(f"Products:      {final_products:,}")
        print(f"Orders:        {final_orders:,}")
        print(f"Order Items:   {final_items:,}")
        print(f"Total time:    {total_elapsed:.2f} seconds")
        print("========================\n")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Seed sample_shop database with realistic e-commerce data."
    )
    parser.add_argument(
        "--small",
        action="store_true",
        help="Generate smaller dataset (1k users, 5k orders) for quick testing",
    )
    parser.add_argument(
        "--medium",
        action="store_true",
        help="Generate medium dataset (10k users, 1k products, 100k orders) for free-tier Neon",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random generator seed for determinism (default: 42)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=True,
        help="Truncate tables before seeding (default: True)",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Database connection URL (defaults to SHOP_ADMIN_DATABASE_URL)",
    )

    args = parser.parse_args()

    db_url = args.database_url or os.getenv("SHOP_ADMIN_DATABASE_URL")
    if not db_url:
        # Import config from app
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from app.core.config import settings

        db_url = settings.shop_admin_database_url

    seed_sample_shop(
        database_url=db_url,
        seed=args.seed,
        small=args.small,
        medium=args.medium,
        reset=args.reset,
    )


if __name__ == "__main__":
    main()
