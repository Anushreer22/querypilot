"""HTTP middlewares for request tracking, structured logging, size limits, and security headers."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import request_id_ctx
from app.core.metrics import metrics_collector

logger = logging.getLogger("querypilot.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assigns unique Request IDs, records telemetry metrics, and emits structured JSON logs."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Honor incoming X-Request-ID if alphanumeric/safe, else generate UUID4
        incoming_req_id = request.headers.get("x-request-id")
        if (
            incoming_req_id
            and len(incoming_req_id) <= 64
            and incoming_req_id.replace("-", "").isalnum()
        ):
            req_id = incoming_req_id
        else:
            req_id = str(uuid.uuid4())

        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            route_path = request.url.path

            # Record telemetry in in-memory metrics
            metrics_collector.record_request(route_path, status_code, latency_ms)

            # Emit structured request log record
            logger.info(
                f"{request.method} {route_path} completed with {status_code} in {latency_ms}ms",
                extra={
                    "route": route_path,
                    "method": request.method,
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                },
            )
            request_id_ctx.reset(token)

        response.headers["x-request-id"] = req_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects defensive HTTP headers preventing MIME-sniffing, framing, and clickjacking."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforces request payload size limits to mitigate denial-of-service memory exhaustion."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        content_length_header = request.headers.get("content-length")
        if content_length_header:
            try:
                content_length = int(content_length_header)
                if content_length > settings.max_request_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request body too large. Maximum allowed size is {settings.max_request_body_bytes} bytes."
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)
