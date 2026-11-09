# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# Stage 1: Build & dependency preparation
# -----------------------------------------------------------------------------
FROM python:3.14-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install minimal build essentials for native extensions (psycopg, argon2-cffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency manifests
COPY pyproject.toml uv.lock* ./

# Install project dependencies into virtual environment
RUN uv sync --frozen --no-dev --no-install-project

# -----------------------------------------------------------------------------
# Stage 2: Minimal runtime image
# -----------------------------------------------------------------------------
FROM python:3.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install runtime libpq for PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r -g 1000 appuser \
    && useradd -m -r -u 1000 -g appuser appuser

# Copy virtual environment and app code
COPY --from=builder /app/.venv /app/.venv
COPY --chown=appuser:appuser . /app

# Create upload directory
RUN mkdir -p /app/uploads /app/static-assets && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
