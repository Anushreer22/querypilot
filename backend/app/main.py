import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

# Initialize structured JSON logging
setup_structured_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context managing database engine cleanup."""
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
