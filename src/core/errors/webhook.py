"""Webhook delivery error."""

import uuid


class WebhookDeliveryError(Exception):
    """Raised when an outbound webhook POST fails.

    Intentionally a plain ``Exception`` (not ``AppError``) — it is an
    internal signal between the delivery service and the Celery task,
    not a user-facing HTTP error.
    """

    def __init__(self, timer_id: uuid.UUID, cause: Exception) -> None:
        self.timer_id = timer_id
        self.cause = cause
        super().__init__(f"Webhook delivery failed for timer {timer_id}: {cause}")

