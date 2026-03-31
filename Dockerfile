FROM python:3.14-slim AS base

WORKDIR /code

# Fast dependency management with uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 1) Install dependencies (cached layer — only rebuilds when lock changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Copy application code and install the project itself
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Default entrypoint: API server
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

