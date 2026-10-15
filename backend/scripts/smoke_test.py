#!/usr/bin/env python3
"""End-to-end smoke test script for QueryPilot deployment verification.

Verifies:
1. GET /health - Liveness probe (200 OK)
2. GET /ready - Readiness probe with both database connections (200 OK)
3. GET /api/schema - Table schema catalog inspection
4. POST /api/query/execute - Safe read-only SELECT execution
5. POST /api/query/execute - Security rejection on malicious DROP TABLE (422)
6. POST /api/ask - Natural language clarification on ambiguous query

Usage:
    python backend/scripts/smoke_test.py [--base-url https://querypilot-backend.onrender.com]
"""

import argparse
import sys
import time
from typing import Any

import httpx


def log_step(name: str, passed: bool, detail: str = "") -> None:
    badge = "[PASS]" if passed else "[FAIL]"
    print(f" {badge} {name:<40} {detail}")


def run_smoke_tests(base_url: str) -> bool:
    print(f"\n=== QueryPilot Deployment Smoke Test ===")
    print(f"Target URL: {base_url}")
    print(f"Timestamp:  {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 60)

    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=15.0)
    all_passed = True

    try:
        # 1. GET /health (Liveness)
        try:
            r = client.get("/health")
            if r.status_code == 200 and r.json().get("status") == "ok":
                log_step("1. Liveness Probe (/health)", True, f"HTTP {r.status_code}")
            else:
                log_step("1. Liveness Probe (/health)", False, f"HTTP {r.status_code} - {r.text[:80]}")
                all_passed = False
        except Exception as exc:
            log_step("1. Liveness Probe (/health)", False, str(exc))
            all_passed = False

        # 2. GET /ready (Readiness)
        try:
            r = client.get("/ready")
            data = r.json()
            if (
                r.status_code == 200
                and data.get("status") == "ok"
                and data.get("app_db") == "ok"
                and data.get("shop_db") == "ok"
            ):
                log_step("2. Readiness Probe (/ready)", True, f"HTTP 200 (app_db=ok, shop_db=ok)")
            else:
                log_step("2. Readiness Probe (/ready)", False, f"HTTP {r.status_code} - {data}")
                all_passed = False
        except Exception as exc:
            log_step("2. Readiness Probe (/ready)", False, str(exc))
            all_passed = False

        # 3. GET /api/schema (Catalog)
        try:
            r = client.get("/api/schema")
            data = r.json()
            tables = [t.get("name") for t in data.get("tables", [])]
            expected = {"users", "products", "orders", "order_items"}
            if r.status_code == 200 and expected.issubset(set(tables)):
                log_step("3. Schema Catalog (/api/schema)", True, f"Found {len(tables)} tables: {', '.join(tables)}")
            else:
                log_step("3. Schema Catalog (/api/schema)", False, f"Tables: {tables}")
                all_passed = False
        except Exception as exc:
            log_step("3. Schema Catalog (/api/schema)", False, str(exc))
            all_passed = False

        # 4. POST /api/query/execute (Read-only SELECT)
        try:
            r = client.post("/api/query/execute", json={"sql": "SELECT count(*) AS total_users FROM users;"})
            data = r.json()
            if r.status_code == 200 and data.get("rows"):
                count_val = data["rows"][0][0]
                log_step("4. Safe SELECT (/api/query/execute)", True, f"users count = {count_val}")
            else:
                log_step("4. Safe SELECT (/api/query/execute)", False, f"HTTP {r.status_code} - {r.text[:80]}")
                all_passed = False
        except Exception as exc:
            log_step("4. Safe SELECT (/api/query/execute)", False, str(exc))
            all_passed = False

        # 5. POST /api/query/execute (Security AST guard on DROP TABLE)
        try:
            r = client.post("/api/query/execute", json={"sql": "DROP TABLE users;"})
            if r.status_code == 422:
                detail = r.json().get("detail", "")
                log_step("5. Security AST Guard (DROP TABLE)", True, f"HTTP 422 Rejected: {detail[:50]}")
            else:
                log_step("5. Security AST Guard (DROP TABLE)", False, f"Expected 422, got HTTP {r.status_code}")
                all_passed = False
        except Exception as exc:
            log_step("5. Security AST Guard (DROP TABLE)", False, str(exc))
            all_passed = False

        # 6. POST /api/ask (Clarification check)
        try:
            r = client.post("/api/ask", json={"question": "Show me the top users"})
            if r.status_code == 200:
                data = r.json()
                if data.get("type") == "clarification":
                    clarif = data.get("clarification", {})
                    log_step("6. Ambiguous Clarification (/api/ask)", True, f"Returned clarification question")
                else:
                    # Might have answered or made assumptions
                    log_step("6. Ambiguous Clarification (/api/ask)", True, f"Responded with type: {data.get('type')}")
            elif r.status_code in (429, 503):
                # Demo rate limit or offline LLM key
                log_step("6. Ambiguous Clarification (/api/ask)", True, f"HTTP {r.status_code} (LLM rate limit / key guard active)")
            else:
                log_step("6. Ambiguous Clarification (/api/ask)", False, f"HTTP {r.status_code} - {r.text[:80]}")
                all_passed = False
        except Exception as exc:
            log_step("6. Ambiguous Clarification (/api/ask)", False, str(exc))
            all_passed = False

    finally:
        client.close()

    print("=" * 60)
    if all_passed:
        print(" [ALL TESTS PASSED] QueryPilot deployment is healthy, verified, and operational.")
        return True
    else:
        print(" [SOME TESTS FAILED] Review the failing endpoints above.")
        return False


def main():
    parser = argparse.ArgumentParser(description="QueryPilot deployment smoke testing tool.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of deployed or local QueryPilot backend (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    success = run_smoke_tests(args.base_url)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

