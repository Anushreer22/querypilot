"""Tests for production safeguards, startup validation, benchmark gating, and daily LLM cap."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.optimize import _optimize_rate_limiter
from app.core.config import Settings
from app.main import lifespan
from app.services.daily_cap import check_daily_llm_cap


@pytest.mark.asyncio
async def test_startup_validation_rejects_cors_wildcard():
    """Startup lifespan in production mode must fail if CORS contains '*'."""
    test_settings = Settings(
        environment="production",
        cors_origins=["*"],
        openai_api_key="sk-test-key",
    )
    with patch("app.main.settings", test_settings):
        dummy_app = FastAPI()
        with pytest.raises(RuntimeError, match="CORS wildcard '\\*' is not permitted"):
            async with lifespan(dummy_app):
                pass


@pytest.mark.asyncio
async def test_startup_validation_rejects_empty_cors():
    """Startup lifespan in production mode must fail if CORS origins list is empty."""
    test_settings = Settings(
        environment="production",
        cors_origins=[],
        openai_api_key="sk-test-key",
    )
    with patch("app.main.settings", test_settings):
        dummy_app = FastAPI()
        with pytest.raises(RuntimeError, match="CORS origins list is empty"):
            async with lifespan(dummy_app):
                pass


@pytest.mark.asyncio
async def test_startup_validation_rejects_missing_openai_key():
    """Startup lifespan in production mode must fail if OPENAI_API_KEY is missing."""
    test_settings = Settings(
        environment="production",
        cors_origins=["https://querypilot.vercel.app"],
        llm_provider="openai",
        openai_api_key="",
    )
    with patch("app.main.settings", test_settings):
        dummy_app = FastAPI()
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
            async with lifespan(dummy_app):
                pass


@pytest.mark.asyncio
async def test_startup_validation_verifies_read_only_setting():
    """Startup lifespan in production mode must fail if sample_shop is not read-only."""
    test_settings = Settings(
        environment="production",
        cors_origins=["https://querypilot.vercel.app"],
        llm_provider="openai",
        openai_api_key="sk-valid-key",
    )

    # Mock shop_engine to return default_transaction_read_only = 'off'
    mock_conn = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = "off"
    mock_conn.execute.return_value = mock_res
    mock_conn.__aenter__.return_value = mock_conn
    mock_conn.__aexit__.return_value = None

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_engine.dispose = AsyncMock()

    with patch("app.main.settings", test_settings), patch("app.main.shop_engine", mock_engine):
        dummy_app = FastAPI()
        with pytest.raises(
            RuntimeError, match="sample_shop role does not enforce default_transaction_read_only=on"
        ):
            async with lifespan(dummy_app):
                pass


@pytest.mark.asyncio
async def test_optimize_benchmark_disabled_returns_403(async_client: httpx.AsyncClient):
    """When benchmark_enabled is False, requesting benchmark=True must return 403 Forbidden."""
    _optimize_rate_limiter._history.clear()
    with patch("app.api.optimize.settings.benchmark_enabled", False):
        response = await async_client.post(
            "/api/optimize",
            json={
                "sql": "SELECT id FROM orders WHERE status = 'shipped';",
                "benchmark": True,
            },
        )
        assert response.status_code == 403
        data = response.json()
        assert "Query benchmarking is disabled on the public demo instance" in data["detail"]


@pytest.mark.asyncio
async def test_optimize_plan_analysis_works_when_benchmark_disabled(
    async_client: httpx.AsyncClient,
):
    """When benchmark_enabled is False, fast plan analysis (benchmark=False) still succeeds."""
    _optimize_rate_limiter._history.clear()
    with patch("app.api.optimize.settings.benchmark_enabled", False):
        response = await async_client.post(
            "/api/optimize",
            json={
                "sql": "SELECT id FROM orders WHERE status = 'shipped';",
                "benchmark": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["improvement_label"] in ("ESTIMATED", "NONE")
        assert any("Benchmark skipped" in note for note in data["notes"])


@pytest.mark.asyncio
async def test_daily_llm_cap_enforcement():
    """check_daily_llm_cap must raise HTTPException 429 when usage reaches the daily cap."""
    with patch("app.services.daily_cap.settings.daily_llm_call_cap", 5):
        # Mock session returning 5 calls today
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("app.services.daily_cap.AppAsyncSessionLocal", return_value=mock_session):
            with pytest.raises(HTTPException) as exc_info:
                await check_daily_llm_cap()
            assert exc_info.value.status_code == 429
            assert "Daily public demo query budget reached" in exc_info.value.detail


@pytest.mark.asyncio
async def test_daily_llm_cap_permits_under_budget():
    """check_daily_llm_cap must not raise when usage is strictly below the daily cap."""
    with patch("app.services.daily_cap.settings.daily_llm_call_cap", 50):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("app.services.daily_cap.AppAsyncSessionLocal", return_value=mock_session):
            # Should complete without error
            await check_daily_llm_cap()
