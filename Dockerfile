# ─────────────────────────────────────────────────────────────
# Project Sentinel — Dockerfile
# ─────────────────────────────────────────────────────────────
# Multi-stage build for the FastAPI application.
# Will be refined in Track 17 (Delivery Readiness).
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for psycopg and pgvector
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency files first for Docker layer caching
COPY pyproject.toml ./

# Install uv and project dependencies
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e .

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "sentinel.main:app", "--host", "0.0.0.0", "--port", "8000"]
