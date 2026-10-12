# Database Architecture: `sample_shop`

This document details the database schema, entity relationships, integrity constraints, security roles, deliberate index omissions, and benchmark query profiles for the `sample_shop` e-commerce database.

---

## 1. Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    users ||--o{ orders : "places (1:N)"
    orders ||--|{ order_items : "contains (1:N)"
    products ||--o{ order_items : "ordered_in (1:N)"

    users {
        bigint id PK
        varchar(255) name
        varchar(255) email UK
        varchar(100) country
        timestamptz created_at
    }

    products {
        bigint id PK
        varchar(255) name
        varchar(100) category
        numeric(10,2) price "CHECK >= 0"
        integer stock "CHECK >= 0"
        timestamptz created_at
    }

    orders {
        bigint id PK
        bigint user_id FK "indexed"
        varchar(50) status "CHECK in statuses"
        numeric(12,2) total_amount "CHECK >= 0"
        timestamptz created_at "unindexed"
    }

    order_items {
        bigint id PK
        bigint order_id FK "CASCADE, unindexed"
        bigint product_id FK "RESTRICT, unindexed"
        integer quantity "CHECK > 0"
        numeric(10,2) unit_price "CHECK >= 0"
    }
```

---

## 2. Table-by-Table Schema Specification

### `users`
Represents registered customer accounts across various geographical regions.
- `id` (`BIGINT`, `PRIMARY KEY`, `IDENTITY`): Unique user identifier.
- `name` (`VARCHAR(255)`, `NOT NULL`): Customer full name.
- `email` (`VARCHAR(255)`, `NOT NULL`, `UNIQUE`): Customer email address enforced by unique index `uq_users_email`.
- `country` (`VARCHAR(100)`, `NOT NULL`): Customer residence country.
- `created_at` (`TIMESTAMPTZ`, `NOT NULL`, default `NOW()`): Account registration timestamp.

### `products`
Catalog of items available for sale across distinct product categories.
- `id` (`BIGINT`, `PRIMARY KEY`, `IDENTITY`): Unique product SKU identifier.
- `name` (`VARCHAR(255)`, `NOT NULL`): Product name and descriptive tags.
- `category` (`VARCHAR(100)`, `NOT NULL`): Category partition (e.g., Electronics, Apparel, Home & Kitchen).
- `price` (`NUMERIC(10, 2)`, `NOT NULL`): Base price with constraint `CHECK (price >= 0)`.
- `stock` (`INTEGER`, `NOT NULL`): Available warehouse inventory with constraint `CHECK (stock >= 0)`.
- `created_at` (`TIMESTAMPTZ`, `NOT NULL`, default `NOW()`): Product addition timestamp.

### `orders`
Customer purchases with financial summaries and order fulfillment status.
- `id` (`BIGINT`, `PRIMARY KEY`, `IDENTITY`): Unique order invoice number.
- `user_id` (`BIGINT`, `NOT NULL`, `FOREIGN KEY -> users.id`):
  - **Index**: `ix_orders_user_id` (the single non-PK secondary index).
  - **ON DELETE Behavior**: `RESTRICT`. Deleting a user who has order history is blocked to preserve financial ledgers, transactional history, and audit compliance.
- `status` (`VARCHAR(50)`, `NOT NULL`): Order state with constraint `CHECK (status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded'))`.
- `total_amount` (`NUMERIC(12, 2)`, `NOT NULL`): Order total sum with constraint `CHECK (total_amount >= 0)`. Guaranteed to strictly match `SUM(quantity * unit_price)` of all corresponding line items.
- `created_at` (`TIMESTAMPTZ`, `NOT NULL`): Order placement timestamp.

### `order_items`
Individual line items purchased within an order.
- `id` (`BIGINT`, `PRIMARY KEY`, `IDENTITY`): Unique line item identifier.
- `order_id` (`BIGINT`, `NOT NULL`, `FOREIGN KEY -> orders.id`):
  - **ON DELETE Behavior**: `CASCADE`. Order line items have no standalone semantic meaning without their parent order. If an order record is purged, its line items are automatically removed.
  - **Index**: Intentionally omitted.
- `product_id` (`BIGINT`, `NOT NULL`, `FOREIGN KEY -> products.id`):
  - **ON DELETE Behavior**: `RESTRICT`. Prevents deletion of catalog products that have historical customer purchases.
  - **Index**: Intentionally omitted.
- `quantity` (`INTEGER`, `NOT NULL`): Quantity purchased with constraint `CHECK (quantity > 0)`.
- `unit_price` (`NUMERIC(10, 2)`, `NOT NULL`): Locked historical item price at time of purchase with constraint `CHECK (unit_price >= 0)`.

---

## 3. Deliberate Index Omissions (Phase 6 Candidates)

To provide realistic optimization opportunities for the QueryPilot AI query planning and index optimization engine (Phase 6), the following critical access paths were **deliberately left unindexed**:

| Column / Relationship | Typical Query Pattern | Impact of Missing Index | Optimization Candidate |
| :--- | :--- | :--- | :--- |
| **`orders.created_at`** | Date-range filters (`WHERE created_at >= NOW() - INTERVAL '30 days'`), monthly aggregations, and chronological sorting. | Forces a **Parallel Sequential Scan** across all 500,000 orders even when filtering down to a 7-day or 30-day window. | B-Tree index: `CREATE INDEX ix_orders_created_at ON orders(created_at);` |
| **`orders.status`** | Order status filtering (`WHERE status = 'delivered'` or `'cancelled'`). | Prevents index filtering on high-frequency status queries; requires scanning every row in the `orders` heap table. | Composite / Partial B-Tree index: `CREATE INDEX ix_orders_status_created ON orders(status, created_at);` |
| **`order_items.order_id`** | Joining `orders` to `order_items` (`orders.id = order_items.order_id`). | Foreign key joins must sequentially scan or hash scan the entire 1.12M+ row `order_items` table. | Foreign Key B-Tree: `CREATE INDEX ix_order_items_order_id ON order_items(order_id);` |
| **`order_items.product_id`** | Joining products to sales line items (`products.id = order_items.product_id`) for category revenue or velocity. | Product-based analytical queries cannot seek line items; forces sequential scans of 1,125,665 line items. | Foreign Key B-Tree: `CREATE INDEX ix_order_items_product_id ON order_items(product_id);` |
| **`products.category`** | Grouping and filtering catalog items (`WHERE category = 'Electronics'`). | Full table scans on `products` when filtering or partitioning by category. | B-Tree index: `CREATE INDEX ix_products_category ON products(category);` |

---

## 4. Benchmark Queries (Verified on 500k Orders / 1.12M Items)

All 10 queries have been executed and verified against the live seeded database. Below are their SQL definitions, descriptions, and actual measured execution times:

### Query 1: Top 5 customers by spending this month
*Finds the highest spending customers in the preceding month using CTE, table join, aggregation, and window ranking.*
- **Runtime**: `450.6 ms`
```sql
WITH current_month_orders AS (
    SELECT 
        o.user_id,
        o.total_amount
    FROM orders o
    WHERE o.created_at >= date_trunc('month', NOW() - INTERVAL '1 month')
      AND o.created_at < date_trunc('month', NOW())
      AND o.status IN ('paid', 'shipped', 'delivered')
)
SELECT 
    u.id AS user_id,
    u.name,
    u.email,
    u.country,
    ROUND(SUM(cmo.total_amount), 2) AS total_spent,
    COUNT(*) AS order_count,
    DENSE_RANK() OVER (ORDER BY SUM(cmo.total_amount) DESC) AS rank
FROM current_month_orders cmo
JOIN users u ON cmo.user_id = u.id
GROUP BY u.id, u.name, u.email, u.country
ORDER BY total_spent DESC
LIMIT 5;
```

---

### Query 2: Monthly order volume and revenue growth trend
*Aggregates delivered orders by month and computes month-over-month revenue percentage change with `LAG()`.*
- **Runtime**: `508.0 ms`
```sql
WITH monthly_stats AS (
    SELECT 
        date_trunc('month', created_at) AS order_month,
        COUNT(*) AS total_orders,
        ROUND(SUM(total_amount), 2) AS gross_revenue
    FROM orders
    WHERE status = 'delivered'
    GROUP BY date_trunc('month', created_at)
)
SELECT 
    to_char(order_month, 'YYYY-MM') AS month,
    total_orders,
    gross_revenue,
    LAG(gross_revenue) OVER (ORDER BY order_month) AS prev_month_revenue,
    ROUND(
        (gross_revenue - LAG(gross_revenue) OVER (ORDER BY order_month)) 
        / NULLIF(LAG(gross_revenue) OVER (ORDER BY order_month), 0) * 100, 
        2
    ) AS mom_growth_pct
FROM monthly_stats
ORDER BY order_month;
```

---

### Query 3: Top 3 products by revenue within each category
*Calculates product-level sales and ranks top performers per category using window `DENSE_RANK() OVER (PARTITION BY category)`.*
- **Runtime**: `711.4 ms`
```sql
WITH product_revenue AS (
    SELECT 
        p.id AS product_id,
        p.name AS product_name,
        p.category,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue,
        SUM(oi.quantity) AS units_sold,
        DENSE_RANK() OVER (
            PARTITION BY p.category 
            ORDER BY SUM(oi.quantity * oi.unit_price) DESC
        ) AS category_rank
    FROM products p
    JOIN order_items oi ON p.id = oi.product_id
    JOIN orders o ON oi.order_id = o.id
    WHERE o.status = 'delivered'
    GROUP BY p.id, p.name, p.category
)
SELECT 
    category,
    category_rank,
    product_name,
    total_revenue,
    units_sold
FROM product_revenue
WHERE category_rank <= 3
ORDER BY category, category_rank;
```

---

### Query 4: Running 90-day cumulative revenue and 7-day rolling average
*Computes daily sales, unbounded cumulative running revenue, and a 7-day moving average using frame specifications.*
- **Runtime**: `259.1 ms`
```sql
WITH daily_revenue AS (
    SELECT 
        created_at::date AS order_date,
        COUNT(*) AS daily_orders,
        ROUND(SUM(total_amount), 2) AS daily_sales
    FROM orders
    WHERE status IN ('paid', 'shipped', 'delivered')
      AND created_at >= NOW() - INTERVAL '90 days'
    GROUP BY created_at::date
)
SELECT 
    order_date,
    daily_orders,
    daily_sales,
    ROUND(SUM(daily_sales) OVER (ORDER BY order_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cumulative_revenue,
    ROUND(AVG(daily_sales) OVER (ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS rolling_7day_avg
FROM daily_revenue
ORDER BY order_date DESC;
```

---

### Query 5: High-value inactive customers (Churn risk)
*Identifies customers with >= 3 historical orders who have not placed any orders in the past 90 days via anti-join `NOT EXISTS`.*
- **Runtime**: `536.8 ms`
```sql
SELECT 
    u.id AS user_id,
    u.name,
    u.email,
    u.country,
    COUNT(o.id) AS lifetime_orders,
    ROUND(SUM(o.total_amount), 2) AS lifetime_spent,
    MAX(o.created_at) AS last_order_date
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE o.status IN ('paid', 'shipped', 'delivered')
  AND NOT EXISTS (
      SELECT 1 
      FROM orders recent_o 
      WHERE recent_o.user_id = u.id 
        AND recent_o.created_at >= NOW() - INTERVAL '90 days'
  )
GROUP BY u.id, u.name, u.email, u.country
HAVING COUNT(o.id) >= 3
ORDER BY lifetime_spent DESC
LIMIT 10;
```

---

### Query 6: Average order value and item quantity by country
*Calculates average order value, basket size, and total sales grouped by country with a `HAVING` volume threshold.*
- **Runtime**: `2,127.7 ms`
```sql
SELECT 
    u.country,
    COUNT(DISTINCT o.id) AS total_orders,
    COUNT(oi.id) AS total_items_sold,
    ROUND(AVG(o.total_amount), 2) AS average_order_value,
    ROUND(AVG(oi.quantity), 2) AS avg_quantity_per_item,
    ROUND(SUM(o.total_amount), 2) AS total_country_revenue
FROM users u
JOIN orders o ON u.id = o.user_id
JOIN order_items oi ON o.id = oi.order_id
WHERE o.status = 'delivered'
GROUP BY u.country
HAVING COUNT(DISTINCT o.id) >= 100
ORDER BY total_country_revenue DESC;
```

---

### Query 7: Products with high cancellation and refund rates
*Aggregates order line items to calculate return/cancellation ratios and financial loss per product via conditional aggregation.*
- **Runtime**: `3,008.9 ms`
```sql
SELECT 
    p.id AS product_id,
    p.name AS product_name,
    p.category,
    COUNT(DISTINCT o.id) AS total_orders_containing_product,
    SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
    SUM(CASE WHEN o.status = 'refunded' THEN 1 ELSE 0 END) AS refunded_orders,
    ROUND(
        (SUM(CASE WHEN o.status IN ('cancelled', 'refunded') THEN 1 ELSE 0 END)::numeric 
        / NULLIF(COUNT(DISTINCT o.id), 0)) * 100, 
        2
    ) AS return_cancel_rate_pct,
    ROUND(SUM(CASE WHEN o.status = 'refunded' THEN oi.quantity * oi.unit_price ELSE 0 END), 2) AS refunded_revenue_loss
FROM products p
JOIN order_items oi ON p.id = oi.product_id
JOIN orders o ON oi.order_id = o.id
GROUP BY p.id, p.name, p.category
HAVING COUNT(DISTINCT o.id) >= 50
ORDER BY return_cancel_rate_pct DESC
LIMIT 10;
```

---

### Query 8: Customer repeat order intervals
*Measures day intervals between consecutive customer orders using window function `LAG(created_at) OVER (PARTITION BY user_id)`.*
- **Runtime**: `1,913.4 ms`
```sql
WITH customer_order_timeline AS (
    SELECT 
        user_id,
        id AS order_id,
        created_at AS current_order_date,
        LAG(created_at) OVER (PARTITION BY user_id ORDER BY created_at) AS previous_order_date
    FROM orders
    WHERE status IN ('paid', 'shipped', 'delivered')
)
SELECT 
    user_id,
    COUNT(*) AS repeat_orders,
    ROUND(AVG(EXTRACT(EPOCH FROM (current_order_date - previous_order_date)) / 86400)::numeric, 1) AS avg_days_between_orders,
    ROUND(MIN(EXTRACT(EPOCH FROM (current_order_date - previous_order_date)) / 86400)::numeric, 1) AS min_days_between_orders,
    ROUND(MAX(EXTRACT(EPOCH FROM (current_order_date - previous_order_date)) / 86400)::numeric, 1) AS max_days_between_orders
FROM customer_order_timeline
WHERE previous_order_date IS NOT NULL
GROUP BY user_id
HAVING COUNT(*) >= 5
ORDER BY avg_days_between_orders ASC
LIMIT 10;
```

---

### Query 9: Low stock products with high 30-day sales velocity
*Identifies catalog items with less than 50 units in stock and estimates remaining inventory days based on 30-day velocity.*
- **Runtime**: `252.0 ms`
```sql
WITH recent_sales AS (
    SELECT 
        oi.product_id,
        SUM(oi.quantity) AS units_sold_30d,
        COUNT(DISTINCT o.id) AS order_count_30d
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.id
    WHERE o.created_at >= NOW() - INTERVAL '30 days'
      AND o.status IN ('paid', 'shipped', 'delivered')
    GROUP BY oi.product_id
)
SELECT 
    p.id AS product_id,
    p.name AS product_name,
    p.category,
    p.stock AS current_stock,
    COALESCE(rs.units_sold_30d, 0) AS units_sold_30d,
    ROUND((p.stock::numeric / NULLIF(rs.units_sold_30d, 0) * 30), 1) AS estimated_days_stock_remaining
FROM products p
JOIN recent_sales rs ON p.id = rs.product_id
WHERE p.stock < 50
ORDER BY estimated_days_stock_remaining ASC, rs.units_sold_30d DESC
LIMIT 10;
```

---

### Query 10: Order status breakdown and gross revenue share
*Calculates order volume percentages and revenue share by order status using window aggregate `SUM(...) OVER ()`.*
- **Runtime**: `143.9 ms`
```sql
SELECT 
    status,
    COUNT(*) AS order_count,
    ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER () * 100, 2) AS order_percentage,
    ROUND(SUM(total_amount), 2) AS total_amount,
    ROUND(SUM(total_amount)::numeric / SUM(SUM(total_amount)) OVER () * 100, 2) AS revenue_share_pct,
    ROUND(AVG(total_amount), 2) AS avg_order_value
FROM orders
GROUP BY status
ORDER BY order_count DESC;
```

---

## 5. PostgreSQL EXPLAIN Execution Plans (Demonstrating Sequential Scans)

Because `orders.created_at`, `orders.status`, and `order_items.product_id` lack secondary indexes, the PostgreSQL query optimizer cannot use Index Scans and must fall back to Parallel Sequential Scans:

### Query 1 EXPLAIN Plan (Sequential Scan on `orders`)
```
Limit  (cost=30632.98..30633.00 rows=5 width=144)
  ->  Sort  (cost=30632.98..30757.98 rows=50000 width=144)
        Sort Key: (round((sum(o.total_amount)), 2)) DESC
        ->  WindowAgg  (cost=28802.50..29802.50 rows=50000 width=144)
              ->  Sort  (cost=28802.50..28927.50 rows=50000 width=104)
                    Sort Key: (sum(o.total_amount)) DESC
                    ->  Finalize GroupAggregate  (cost=15514.83..22163.09 rows=50000 width=104)
                          Group Key: u.id
                          ->  Gather Merge  (cost=15514.83..21097.39 rows=44070 width=104)
                                Workers Planned: 2
                                ->  Partial GroupAggregate  (cost=14514.81..15010.60 rows=22035 width=104)
                                      Group Key: u.id
                                      ->  Sort  (cost=14514.81..14569.90 rows=22035 width=70)
                                            Sort Key: u.id
                                            ->  Hash Join  (cost=1781.00..12925.26 rows=22035 width=70)
                                                  Hash Cond: (o.user_id = u.id)
                                                  ->  Parallel Seq Scan on orders o  (cost=0.00..11086.42 rows=22035 width=14)
                                                        Filter: (((status)::text = ANY ('{paid,shipped,delivered}'::text[])) AND (created_at < date_trunc('month'::text, now())) AND (created_at >= date_trunc('month'::text, (now() - '1 mon'::interval))))
                                                  ->  Hash  (cost=1156.00..1156.00 rows=50000 width=64)
                                                        ->  Seq Scan on users u  (cost=0.00..1156.00 rows=50000 width=64)
```
> **Observation**: Notice `Parallel Seq Scan on orders o (cost=0.00..11086.42 rows=22035)`. Filtering on `created_at` and `status` scans all 500k rows in `orders` sequentially.

---

### Query 3 EXPLAIN Plan (Sequential Scans on `order_items` and `orders`)
```
Incremental Sort  (cost=32199.41..32543.12 rows=5000 width=85)
  Sort Key: product_revenue.category, product_revenue.category_rank
  Presorted Key: product_revenue.category
  ->  Subquery Scan on product_revenue  (cost=32198.02..32360.52 rows=5000 width=85)
        ->  WindowAgg  (cost=32198.02..32310.52 rows=5000 width=125)
              Run Condition: (dense_rank() OVER (?) <= 3)
              ->  Sort  (cost=32198.02..32210.52 rows=5000 width=85)
                    Sort Key: p.category, (sum(((oi.quantity)::numeric * oi.unit_price))) DESC
                    ->  Finalize HashAggregate  (cost=31828.33..31890.83 rows=5000 width=85)
                          Group Key: p.id
                          ->  Gather  (cost=30665.83..31728.33 rows=10000 width=85)
                                Workers Planned: 2
                                ->  Partial HashAggregate  (cost=29665.83..29728.33 rows=5000 width=85)
                                      Group Key: p.id
                                      ->  Hash Join  (cost=9225.58..25449.28 rows=337324 width=55)
                                            Hash Cond: (oi.product_id = p.id)
                                            ->  Parallel Hash Join  (cost=9053.08..24390.56 rows=337324 width=18)
                                                  Hash Cond: (oi.order_id = o.id)
                                                  ->  Parallel Seq Scan on order_items oi  (cost=0.00..14106.27 rows=469027 width=26)
                                                  ->  Parallel Hash  (cost=7180.17..7180.17 rows=149833 width=8)
                                                        ->  Parallel Seq Scan on orders o  (cost=0.00..7180.17 rows=149833 width=8)
                                                              Filter: ((status)::text = 'delivered'::text)
                                            ->  Hash  (cost=110.00..110.00 rows=5000 width=45)
                                                  ->  Seq Scan on products p  (cost=0.00..110.00 rows=5000 width=45)
```
> **Observation**: Both `Parallel Seq Scan on order_items oi (cost=0.00..14106.27 rows=469027)` and `Parallel Seq Scan on orders o (cost=0.00..7180.17 rows=149833)` appear because `order_items.order_id` and `order_items.product_id` lack B-Tree indexes.

