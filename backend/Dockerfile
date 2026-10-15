# ==============================================================================
# Multi-stage production Dockerfile for QueryPilot Backend
# Base: Python 3.12-slim | Non-root execution | Minimal footprint
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install compilation prerequisites for C extensions (e.g. psycopg, pydantic core)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy production requirements and build isolated wheels
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: Production Runtime
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Install minimal runtime system libraries and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user and group (appuser:appuser, UID:GID 1000:1000)
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/bash -m appuser

WORKDIR /app

# Install wheels built in builder stage (zero build tools installed in runtime)
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy application source code, Alembic migrations, and scripts
COPY --chown=appuser:appuser app/ /app/app/
COPY --chown=appuser:appuser alembic/ /app/alembic/
COPY --chown=appuser:appuser alembic_shop/ /app/alembic_shop/
COPY --chown=appuser:appuser alembic.ini /app/alembic.ini
COPY --chown=appuser:appuser alembic_shop.ini /app/alembic_shop.ini
COPY --chown=appuser:appuser scripts/ /app/scripts/

# Ensure runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    ENVIRONMENT=production

# Switch to non-root execution
USER appuser

# Expose default HTTP port
EXPOSE 8000

# Docker healthcheck querying /health liveness probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start command respecting dynamic PORT provided by host (e.g. Render, Railway)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]

