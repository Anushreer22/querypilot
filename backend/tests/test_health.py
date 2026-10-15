from unittest.mock import patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_liveness(async_client: httpx.AsyncClient):
    """Test /health liveness probe returns 200 OK without database overhead."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_live_dbs_up(async_client: httpx.AsyncClient):
    """Test /ready readiness probe when both databases are reachable (returns 200 OK)."""
    response = await async_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_db"] == "ok"
    assert data["shop_db"] == "ok"


@pytest.mark.asyncio
async def test_ready_mocked_db_failure(async_client: httpx.AsyncClient):
    """Test /ready readiness probe when one database connection fails (returns 503 Service Unavailable)."""

    async def mock_check(engine):
        # Simulate app_engine failure while shop_engine is ok
        from app.db.session import app_engine

        if engine is app_engine:
            return "error"
        return "ok"

    with patch("app.api.health.check_engine_connection", side_effect=mock_check):
        response = await async_client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "error"
        assert data["app_db"] == "error"
        assert data["shop_db"] == "ok"


@pytest.mark.asyncio
async def test_ready_mocked_all_db_failure(async_client: httpx.AsyncClient):
    """Test /ready readiness probe when both database connections fail (returns 503 Service Unavailable)."""
    with patch("app.api.health.check_engine_connection", return_value="error"):
        response = await async_client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "error"
        assert data["app_db"] == "error"
        assert data["shop_db"] == "error"
