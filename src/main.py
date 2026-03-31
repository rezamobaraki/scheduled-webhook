"""FastAPI application entry-point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.errors import register_exception_handlers
from src.core.logging import setup_logging
from src.routers import timers_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: startup / shutdown hooks."""
    setup_logging()
    yield


app = FastAPI(
    title="Timer Service",
    description="Delayed webhook execution service",
    version="1.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(timers_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}

