import uuid

import httpx

from src.core import Logger
from src.core.configs import settings
from src.core.errors import WebhookDeliveryError

logger = Logger.get(__name__)


class WebhookService:
    __slots__ = ("_timeout",)

    def __init__(self, timeout: int = settings.webhook.timeout) -> None:
        self._timeout = timeout

    def deliver(self, timer_id: uuid.UUID, url: str) -> None:
        try:
            response = httpx.post(
                url,
                json={"id": str(timer_id)},
                headers={
                    "Idempotency-Key": str(timer_id),
                    "X-Timer-Id": str(timer_id),
                },
                timeout=self._timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WebhookDeliveryError(timer_id, cause=exc) from exc

        logger.info(f"Webhook delivered for timer:{timer_id} Url: {url}")
