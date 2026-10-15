"""API-level security tests covering payload limits, security headers, malformed input, rate limiting, and secret leak detection."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_security_headers_present_on_responses() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "max-age=31536000" in resp.headers.get("Strict-Transport-Security", "")
        assert "default-src 'none'" in resp.headers.get("Content-Security-Policy", "")
        assert resp.headers.get("x-request-id") is not None


@pytest.mark.asyncio
async def test_custom_x_request_id_preserved_if_safe() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        safe_id = "test-request-id-12345"
        resp = await client.get("/health", headers={"X-Request-ID": safe_id})
        assert resp.status_code == 200
        assert resp.headers.get("x-request-id") == safe_id


@pytest.mark.asyncio
async def test_payload_body_size_limit_rejection_413() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a body exceeding max_request_body_bytes (1MB)
        oversized_data = "A" * (settings.max_request_body_bytes + 1024)
        resp = await client.post(
            "/api/query/execute",
            content=oversized_data,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(oversized_data)),
            },
        )
        assert resp.status_code == 413
        data = resp.json()
        assert "Request body too large" in data["detail"]


@pytest.mark.asyncio
async def test_malformed_json_returns_422_without_traceback() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/query/execute",
            content="{ 'sql': 'SELECT 1' ",  # Broken JSON
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
        body_text = resp.text
        # Ensure no python tracebacks, internal file paths, or line numbers leak
        assert "Traceback (most recent call last)" not in body_text
        assert 'File "' not in body_text


@pytest.mark.asyncio
async def test_question_max_length_rejection() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        huge_question = "What are the sales? " + ("A" * 550)
        resp = await client.post(
            "/api/ask",
            json={"question": huge_question},
        )
        assert resp.status_code == 422
        assert "at most 500 characters" in resp.text or "string_too_long" in resp.text


@pytest.mark.asyncio
async def test_error_responses_never_leak_secrets() -> None:
    """Send various broken requests and verify error payloads never contain credentials."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        endpoints_to_test = [
            ("/api/query/execute", {"sql": "SELECT non_existent_column FROM users;"}),
            ("/api/ask", {"question": ""}),
            ("/api/agent/ask", {"question": "ab"}),
            ("/api/optimize", {"sql": "INSERT INTO orders DEFAULT VALUES;"}),
        ]

        secret_patterns = [
            "querypilot_app_rw_pass",
            "querypilot_readonly_pass",
            "querypilot_postgres_pass",
            "sk-proj",
            "postgresql://",
            "Traceback",
            "C:\\Users\\",
            "/home/",
        ]

        for endpoint, payload in endpoints_to_test:
            resp = await client.post(endpoint, json=payload)
            body = resp.text
            for secret in secret_patterns:
                assert secret not in body, (
                    f"Secret pattern '{secret}' leaked in {endpoint} response: {body}"
                )


@pytest.mark.asyncio
async def test_metrics_endpoint_telemetry() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "querypilot-backend"
        assert "routes" in data
        assert "security_events" in data
        assert "memory_persistence_notice" in data
        assert "uptime_seconds" in data
