import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.core.errors import WebhookDeliveryError
from src.services.webhook import WebhookService


def test_deliver_sends_idempotency_headers():
    timer_id = uuid.uuid4()
    response = MagicMock()

    with patch("src.services.webhook.httpx.post", return_value=response) as mock_post:
        WebhookService(timeout=7).deliver(timer_id, "https://example.com/webhook")

    mock_post.assert_called_once_with(
        "https://example.com/webhook",
        json={"id": str(timer_id)},
        headers={
            "Idempotency-Key": str(timer_id),
            "X-Timer-Id": str(timer_id),
        },
        timeout=7,
        follow_redirects=True,
    )
    response.raise_for_status.assert_called_once_with()


def test_deliver_wraps_httpx_errors():
    timer_id = uuid.uuid4()

    with (
        patch(
        "src.services.webhook.httpx.post",
        side_effect=httpx.ConnectError("boom"),
        ),
        pytest.raises(WebhookDeliveryError) as exc_info,
    ):
        WebhookService().deliver(timer_id, "https://example.com/webhook")

    assert exc_info.value.timer_id == timer_id
