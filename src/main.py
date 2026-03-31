from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.responses import RedirectResponse

from src.core import Logger
from src.core.database import async_engine
from src.core.errors import register_exception_handlers
from src.routers import timers_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: startup / shutdown hooks."""
    Logger.setup()
    yield
    # Dispose the async engine so all pooled connections are closed cleanly.
    await async_engine.dispose()


app = FastAPI(
    title="Timer Service",
    description="Delayed webhook execution service",
    version="1.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(timers_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
