# ═══════════════════════════════════════════════════════════════════════════════
# Timer Service — Multi-stage Dockerfile
#
# Stages:
#   1. builder  — install dependencies + build the wheel (heavy, throwaway)
#   2. runtime  — minimal image with only the installed packages + app code
#
# Best practices:
#   • Multi-stage build (small final image, no build tooling in prod)
#   • Non-root user (principle of least privilege)
#   • Layer ordering optimised for Docker cache (deps → code)
#   • .dockerignore excludes .git, tests, docs, .env, IDE files
#   • OCI metadata labels
#   • No dev dependencies in the final image
#   • PYTHONDONTWRITEBYTECODE / PYTHONUNBUFFERED for containers
#   • Healthchecks defined per-service in docker-compose.yml
# ═══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

WORKDIR /build

# Install uv for fast, reproducible dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 1) Copy only dependency manifests first (maximises layer cache hits)
COPY pyproject.toml uv.lock ./

# 2) Install production dependencies into a virtual-env we can copy later
RUN uv sync --frozen --no-dev --no-install-project

# 3) Copy application source and install the project itself
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./
RUN uv sync --frozen --no-dev


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

# ── OCI metadata ─────────────────────────────────────────────────────────────
LABEL org.opencontainers.image.title="Timer Service" \
      org.opencontainers.image.description="Delayed webhook execution service" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.source="https://github.com/your-org/timer-service"

# ── Environment hardening ────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── Non-root user ────────────────────────────────────────────────────────────
RUN groupadd --system appgroup && \
    useradd  --system --gid appgroup --no-create-home appuser

# ── Copy built artefacts from the builder stage ─────────────────────────────
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/src   /app/src
COPY --from=builder /build/migrations /app/migrations
COPY --from=builder /build/alembic.ini /app/alembic.ini

# Put the virtual-env on PATH so `python`, `uvicorn`, `celery`, `alembic`
# resolve to the installed versions without needing `uv run`.
ENV PATH="/app/.venv/bin:$PATH"

# ── Switch to non-root ──────────────────────────────────────────────────────
USER appuser

EXPOSE 8000

# ── Default entrypoint: API server ──────────────────────────────────────────
# Healthchecks are defined per-service in docker-compose.yml since
# api / worker / beat each need different probes.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
