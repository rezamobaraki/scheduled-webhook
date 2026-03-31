"""Structured logging configuration powered by ``structlog``.

Call :func:`setup_logging` once during the application lifespan
(FastAPI startup or Celery worker init) — **not** at module level —
so tests and import ordering stay predictable.
"""

import logging
import sys

import structlog
from structlog.processors import JSONRenderer, TimeStamper, add_log_level
from structlog.stdlib import LoggerFactory


def setup_logging() -> structlog.stdlib.BoundLogger:
    """Configure ``structlog`` with JSON output and return a root logger.

    * ISO-8601 timestamps for machine-parseable logs.
    * JSON renderer for easy ``jq`` / log-aggregator consumption.
    * Stdlib root handler wired to ``stdout`` (container best-practice).
    """
    structlog.configure(
        processors=[
            TimeStamper(fmt="iso"),
            add_log_level,
            JSONRenderer(),
        ],
        logger_factory=LoggerFactory(),
    )

    handler = logging.StreamHandler(sys.stdout)
    root = logging.getLogger()
    # Avoid duplicate handlers when called more than once (e.g. tests).
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return structlog.get_logger()

