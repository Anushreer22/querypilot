import { http, HttpResponse } from "msw";

export const handlers = [
  // GET /ready & /health
  http.get("*/ready", () => {
    return HttpResponse.json({
      status: "ok",
      app_db: "ok",
      shop_db: "ok",
    });
  }),
  http.get("*/health", () => {
    return HttpResponse.json({
      status: "ok",
      app_db: "ok",
      shop_db: "ok",
    });
  }),

  // GET /api/schema
  http.get("*/api/schema", () => {
    return HttpResponse.json({
      tables: [
        {
          name: "users",
          primary_key: ["id"],
          foreign_keys: [],
          columns: [
            { name: "id", type: "BIGINT", nullable: false, default: null },
            { name: "name", type: "VARCHAR(255)", nullable: false, default: null },
            { name: "email", type: "VARCHAR(255)", nullable: false, default: null },
            { name: "country", type: "VARCHAR(100)", nullable: false, default: null },
            { name: "created_at", type: "TIMESTAMPTZ", nullable: false, default: "now()" },
          ],
        },
        {
          name: "orders",
          primary_key: ["id"],
          foreign_keys: [
            {
              constrained_columns: ["user_id"],
              referred_table: "users",
              referred_columns: ["id"],
            },
          ],
          columns: [
            { name: "id", type: "BIGINT", nullable: false, default: null },
            { name: "user_id", type: "BIGINT", nullable: false, default: null },
            { name: "status", type: "VARCHAR(50)", nullable: false, default: null },
            { name: "total_amount", type: "NUMERIC(12,2)", nullable: false, default: null },
            { name: "created_at", type: "TIMESTAMPTZ", nullable: false, default: null },
          ],
        },
      ],
    });
  }),

  // POST /api/query/execute
  http.post("*/api/query/execute", async ({ request }) => {
    const body = (await request.json()) as { sql: string };
    if (body.sql.includes("DELETE") || body.sql.includes("DROP")) {
      return HttpResponse.json(
        { detail: "SQL validation rejected: Mutations not allowed" },
        { status: 422 }
      );
    }
    if (body.sql.includes("SYNTAX_ERROR")) {
      return HttpResponse.json(
        { detail: "syntax error at or near 'SYNTAX_ERROR'" },
        { status: 400 }
      );
    }
    if (body.sql.includes("TIMEOUT")) {
      return HttpResponse.json(
        { detail: "canceling statement due to statement timeout" },
        { status: 504 }
      );
    }
    return HttpResponse.json({
      columns: ["id", "name", "email"],
      rows: [
        { id: 1, name: "Alice", email: "alice@example.com" },
        { id: 2, name: "Bob", email: "bob@example.com" },
      ],
      row_count: 2,
      duration_ms: 12.5,
      limit_injected: false,
      truncated: false,
      sanitized_sql: body.sql,
    });
  }),

  // GET /api/query/history
  http.get("*/api/query/history", () => {
    return HttpResponse.json({
      items: [
        {
          id: 101,
          source: "manual",
          sql_text: "SELECT id, name FROM users LIMIT 10;",
          status: "success",
          duration_ms: 8.2,
          row_count: 10,
          created_at: new Date().toISOString(),
        },
        {
          id: 102,
          source: "ask",
          sql_text: "SELECT * FROM orders WHERE status = 'delivered';",
          status: "rejected",
          duration_ms: 0.0,
          error_message: "Prohibited syntax",
          created_at: new Date().toISOString(),
        },
      ],
      total: 2,
    });
  }),

  // POST /api/ask
  http.post("*/api/ask", async ({ request }) => {
    const body = (await request.json()) as { question: string };
    if (body.question.includes("ambiguous")) {
      return HttpResponse.json({
        question: body.question,
        explanation: "Question needs clarification.",
        assumptions: [],
        status: "clarification",
        clarification: {
          clarification_question: "Did you mean orders placed this year or all time?",
        },
        repaired: false,
      });
    }
    return HttpResponse.json({
      question: body.question,
      sql: "SELECT id, name FROM products ORDER BY price DESC LIMIT 5;",
      explanation: "Fetched the top 5 highest-priced catalog products.",
      assumptions: ["Assumed sorting by product price descending"],
      results: {
        columns: ["id", "name"],
        rows: [{ id: 1, name: "Luxury Watch" }],
        row_count: 1,
        duration_ms: 5.4,
        truncated: false,
      },
      status: "success",
      repaired: false,
    });
  }),

  // POST /api/agent/ask
  http.post("*/api/agent/ask", async ({ request }) => {
    const body = (await request.json()) as { question: string };
    return HttpResponse.json({
      run_id: "test-run-123",
      question: body.question,
      status: "completed",
      final_answer: "Found 1 luxury watch in inventory.",
      sql: "SELECT id, name FROM products WHERE id = 1;",
      step_count: 2,
      total_duration_ms: 45.2,
      assumptions: [],
      steps: [
        {
          step: 1,
          tool: "inspect_schema",
          arguments: { table: "products" },
          status: "ok",
          duration_ms: 10.0,
          summary: "Inspected products table schema",
        },
        {
          step: 2,
          tool: "execute_readonly_query",
          arguments: { sql: "SELECT id, name FROM products WHERE id = 1;" },
          status: "ok",
          duration_ms: 15.0,
          summary: "Executed query returning 1 row",
        },
      ],
    });
  }),

  // GET /api/agent/runs/:run_id
  http.get("*/api/agent/runs/:runId", ({ params }) => {
    return HttpResponse.json({
      run: {
        id: params.runId,
        question: "What are top products?",
        status: "completed",
        final_answer: "Top products listed.",
        step_count: 2,
        total_duration_ms: 50.0,
        created_at: new Date().toISOString(),
      },
      actions: [
        {
          step: 1,
          tool: "inspect_schema",
          arguments: { table: "products" },
          status: "ok",
          duration_ms: 12.0,
          summary: "Inspected schema",
        },
      ],
    });
  }),

  // POST /api/optimize
  http.post("*/api/optimize", async ({ request }) => {
    const body = (await request.json()) as { sql: string; benchmark?: boolean };
    if (body.sql.includes("LOCKED")) {
      return HttpResponse.json(
        { detail: "A query benchmark is already running on sample_shop_bench." },
        { status: 409 }
      );
    }
    if (body.sql.includes("OFFLINE")) {
      return HttpResponse.json(
        { detail: "Benchmark copy database (sample_shop_bench) is unavailable." },
        { status: 503 }
      );
    }

    return HttpResponse.json({
      sql_executed: body.sql,
      planning_time_ms: 1.2,
      execution_time_ms: 4.5,
      total_cost: 150.0,
      plan_summary: "Execution plan root: Limit. Found 1 bottleneck.",
      findings: [
        {
          type: "seq_scan_large_table",
          severity: "warning",
          plan_node: "Seq Scan",
          table: "orders",
          columns: ["created_at"],
          evidence: { rows_read: 3000 },
          explanation: "Sequential scan on orders. Missing index on created_at.",
        },
      ],
      suggestions: [
        {
          id: "ix_orders_created_at",
          table: "orders",
          columns: ["created_at"],
          index_type: "btree",
          predicate: null,
          ddl: 'CREATE INDEX "ix_orders_created_at" ON "orders" ("created_at");',
          reasoning: "Indexes chronological range lookups.",
          estimated_benefit: "ESTIMATED: High speedup.",
          estimated_risk: "Low risk.",
          existing: false,
        },
      ],
      benchmark: body.benchmark
        ? {
            candidate_index_name: "ix_orders_created_at",
            candidate_ddl: 'CREATE INDEX "ix_orders_created_at" ON "orders" ("created_at");',
            baseline_stats: {
              iterations: 7,
              timings_ms: [4.0, 4.2, 4.5, 4.6, 4.7, 4.8, 5.0],
              median_ms: 4.6,
              p95_ms: 4.9,
              min_ms: 4.0,
              max_ms: 5.0,
              stddev_ms: 0.35,
            },
            optimized_stats: {
              iterations: 7,
              timings_ms: [2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4],
              median_ms: 3.1,
              p95_ms: 3.3,
              min_ms: 2.8,
              max_ms: 3.4,
              stddev_ms: 0.2,
            },
            speedup_factor: 1.48,
            index_used: true,
            new_plan_node: "Index Scan",
            index_size_mb: 0.15,
            results_match: true,
            improvement_label: "MEASURED",
            conclusion: "Statistically significant improvement: 1.48x speedup.",
          }
        : null,
      improvement_label: body.benchmark ? "MEASURED" : "ESTIMATED",
      notes: ["Plan analyzed in read-only transaction."],
    });
  }),
];

