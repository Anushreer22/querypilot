import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.agent import router as agent_router
from app.api.ask import router as ask_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.optimize import router as optimize_router
from app.api.query import router as query_router
from app.api.schema import router as schema_router
from app.core.config import settings
from app.core.logging import request_id_ctx, setup_structured_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.db.session import app_engine, bench_admin_engine, bench_engine, shop_engine

logger = logging.getLogger(__name__)

# Initialize structured JSON logging
setup_structured_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context managing startup validation and database engine cleanup."""
    # Production startup validation
    if settings.environment == "production":
        logger.info("Executing strict production startup validations...")

        # 1. CORS validation: no wildcard, non-empty
        origins = settings.cors_origins
        if not origins:
            raise RuntimeError("Production configuration error: CORS origins list is empty.")
        if "*" in origins:
            raise RuntimeError(
                "Production security violation: CORS wildcard '*' is not permitted in production."
            )

        # 2. Required LLM secret validation
        if settings.llm_provider == "openai" and not settings.openai_api_key:
            raise RuntimeError(
                "Production configuration error: OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'."
            )
        elif settings.llm_provider == "gemini" and not settings.gemini_api_key:
            raise RuntimeError(
                "Production configuration error: GEMINI_API_KEY is required when LLM_PROVIDER is 'gemini'."
            )

        # 3. Readonly database role safety validation
        try:
            async with shop_engine.connect() as conn:
                res = await conn.execute(text("SHOW default_transaction_read_only;"))
                ro_val = res.scalar_one_or_none()
                if ro_val != "on":
                    raise RuntimeError(
                        f"Production security violation: sample_shop role does not enforce default_transaction_read_only=on (got '{ro_val}')."
                    )

                # Attempt an INSERT that must fail
                try:
                    await conn.execute(
                        text("INSERT INTO users (email, name) VALUES ('test@example.com', 'Test');")
                    )
                    raise RuntimeError(
                        "Production security violation: sample_shop role permitted an INSERT operation!"
                    )
                except RuntimeError:
                    raise
                except Exception:  # noqa: BLE001
                    # Expected to fail due to read-only transaction or permissions
                    logger.info("Verified sample_shop read-only enforcement: write rejected as expected.")
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Production startup verification failed on sample_shop: {exc}"
            ) from exc

        logger.info("Production startup validations passed successfully.")

    yield
    # Clean up database engine connection pools on shutdown
    await app_engine.dispose()
    await shop_engine.dispose()
    await bench_engine.dispose()
    await bench_admin_engine.dispose()


app = FastAPI(
    title="QueryPilot API",
    version="0.1.0",
    description="QueryPilot backend service - AI database engineer",
    lifespan=lifespan,
)


# Global unhandled exception handler to prevent leaking internal traces or credentials
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    req_id = request_id_ctx.get() or "unknown"
    logging.getLogger("querypilot.error").error(
        f"Unhandled internal server error on {request.method} {request.url.path}: {exc}",
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred.", "request_id": req_id},
    )


# Middlewares (evaluated bottom-to-top on request, top-to-bottom on response)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# Enable CORS for frontend client (e.g. http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(schema_router)
app.include_router(query_router)
app.include_router(ask_router)
app.include_router(agent_router)
app.include_router(optimize_router)
app.include_router(metrics_router)

if __name__ == "__main__":
    import sys

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        loop="asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto",
    )
