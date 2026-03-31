"""Tests for the Timer REST API.

Celery is mocked — these tests verify the HTTP contract only.
"""

import uuid

from httpx import AsyncClient

from tests.conftest import make_timer_payload


class TestCreateTimer:
    """``POST /timer`` — create a new timer."""

    async def test_returns_201_with_id_and_time_left(self, client: AsyncClient):
        resp = await client.post("/timer", json=make_timer_payload(seconds=120))
        assert resp.status_code == 201
        body = resp.json()
        uuid.UUID(body["id"])  # valid UUID
        assert body["time_left"] == 120

    async def test_complex_duration(self, client: AsyncClient):
        payload = make_timer_payload(hours=1, minutes=30, seconds=45)
        resp = await client.post("/timer", json=payload)
        assert resp.status_code == 201
        assert resp.json()["time_left"] == 1 * 3600 + 30 * 60 + 45

    async def test_zero_delay_fires_immediately(self, client: AsyncClient):
        resp = await client.post("/timer", json=make_timer_payload(seconds=0))
        assert resp.status_code == 201
        assert resp.json()["time_left"] == 0

    async def test_dispatches_celery_task(
        self,
        client: AsyncClient,
        mock_fire_webhook,
    ):
        await client.post("/timer", json=make_timer_payload())
        mock_fire_webhook.assert_called_once()

    # ── Validation ───────────────────────────────────────────────────────

    async def test_rejects_negative_hours(self, client: AsyncClient):
        resp = await client.post("/timer", json=make_timer_payload(hours=-1))
        assert resp.status_code == 422

    async def test_rejects_negative_seconds(self, client: AsyncClient):
        resp = await client.post("/timer", json=make_timer_payload(seconds=-5))
        assert resp.status_code == 422

    async def test_rejects_invalid_url(self, client: AsyncClient):
        payload = make_timer_payload()
        payload["url"] = "not-a-url"
        resp = await client.post("/timer", json=payload)
        assert resp.status_code == 422

    async def test_rejects_missing_url(self, client: AsyncClient):
        resp = await client.post(
            "/timer",
            json={"hours": 0, "minutes": 0, "seconds": 10},
        )
        assert resp.status_code == 422

    async def test_rejects_excessive_duration(self, client: AsyncClient):
        resp = await client.post(
            "/timer",
            json=make_timer_payload(hours=31 * 24),
        )
        assert resp.status_code == 422

    async def test_rejects_empty_body(self, client: AsyncClient):
        resp = await client.post("/timer", json={})
        assert resp.status_code == 422


# ── GET /timer/{id} ─────────────────────────────────────────────────────────


class TestGetTimer:
    """``GET /timer/{timer_id}`` — get timer status."""

    async def test_returns_timer_with_time_left(self, client: AsyncClient):
        create = await client.post("/timer", json=make_timer_payload(seconds=300))
        timer_id = create.json()["id"]

        resp = await client.get(f"/timer/{timer_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == timer_id
        assert 298 <= body["time_left"] <= 300  # ±2 s tolerance

    async def test_expired_timer_returns_zero(self, client: AsyncClient):
        create = await client.post("/timer", json=make_timer_payload(seconds=0))
        timer_id = create.json()["id"]

        resp = await client.get(f"/timer/{timer_id}")
        assert resp.json()["time_left"] == 0

    async def test_returns_404_for_unknown_id(self, client: AsyncClient):
        resp = await client.get(f"/timer/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_returns_422_for_bad_uuid(self, client: AsyncClient):
        resp = await client.get("/timer/not-a-uuid")
        assert resp.status_code == 422


# ── Health ───────────────────────────────────────────────────────────────────


class TestHealth:
    """``GET /health`` — liveness probe."""

    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
