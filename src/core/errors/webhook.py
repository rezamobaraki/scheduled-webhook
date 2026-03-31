import uuid


class WebhookDeliveryError(Exception):
    def __init__(self, timer_id: uuid.UUID, cause: Exception) -> None:
        self.timer_id = timer_id
        self.cause = cause
        super().__init__(f"Webhook delivery failed for timer {timer_id}: {cause}")
