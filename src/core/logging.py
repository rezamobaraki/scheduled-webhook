import logging
import sys

import structlog
from structlog.processors import JSONRenderer, TimeStamper, add_log_level
from structlog.stdlib import LoggerFactory


class Logger:
    """Structured logging powered by ``structlog``.
    Usage:

        from src.core.logging import Logger

        Logger.setup()                      # once at startup
        logger = Logger.get(__name__)       # per module
        logger.info("timer created", timer_id="abc-123")
    """

    @classmethod
    def setup(cls) -> None:
        structlog.configure(
            processors=[
                TimeStamper(fmt="iso"),
                add_log_level,
                JSONRenderer(),
            ],
            logger_factory=LoggerFactory(),
        )

        root = logging.getLogger()
        if not root.handlers:
            root.addHandler(logging.StreamHandler(sys.stdout))
        root.setLevel(logging.INFO)

        # Silence noisy third-party loggers
        logging.getLogger("uvicorn.access").handlers.clear()
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    @classmethod
    def get(cls, name: str | None = None) -> structlog.stdlib.BoundLogger:
        return structlog.get_logger(name) if name else structlog.get_logger()
