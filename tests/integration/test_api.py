"""Integration tests for the Timer REST API.

Requires PostgreSQL + Redis via Docker. Celery is mocked — these tests
verify the full HTTP → service → repository → DB round-trip.

Test scenarios are loaded from ``tests/data/timer_scenarios.json`` so that
adding a new edge-case never requires touching test logic.
"""

import json
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.conftest import make_timer_payload

# ── Load test scenarios from JSON seeder ─────────────────────────────────────

_SCENARIOS_PATH = Path(__file__).parents[1] / "data" / "timer_scenarios.json"
_SCENARIOS = json.loads(_SCENARIOS_PATH.read_text())

_VALID_CASES = _SCENARIOS["create_timer"]["valid"]
_INVALID_CASES = _SCENARIOS["create_timer"]["invalid"]
_BAD_ID_CASES = _SCENARIOS["retrieve_timer"]["invalid_ids"]


# ── POST /timer ──────────────────────────────────────────────────────────────


class TestCreateTimer:
    """``POST /timer`` — create a new timer."""

    @pytest.mark.parametrize(
        "scenario",
        _VALID_CASES,
        ids=[c["id"] for c in _VALID_CASES],
    )
    async def test_valid_creation(self, client: AsyncClient, scenario: dict):
        resp = await client.post("/timer", json=scenario["payload"])
        assert resp.status_code == scenario["expected_status"]
        body = resp.json()
        uuid.UUID(body["id"])  # must be a valid UUID
        assert body["time_left"] == scenario["expected_time_left"]

    async def test_dispatches_celery_task(
        self,
        client: AsyncClient,
        mock_fire_webhook,
    ):
        await client.post("/timer", json=make_timer_payload())
        mock_fire_webhook.assert_called_once()

    # ── Invalid inputs (data-driven from JSON) ───────────────────────────

    @pytest.mark.parametrize(
        "scenario",
        _INVALID_CASES,
        ids=[c["id"] for c in _INVALID_CASES],
    )
    async def test_invalid_creation(self, client: AsyncClient, scenario: dict):
        payload = scenario["payload"]
        if payload is None:
            resp = await client.post(
                "/timer",
                content="null",
                headers={"Content-Type": "application/json"},
            )
        else:
            resp = await client.post("/timer", json=payload)
        assert resp.status_code == scenario["expected_status"]

    async def test_rejects_non_json_body(self, client: AsyncClient):
        """Plain text instead of JSON is rejected."""
        resp = await client.post(
            "/timer",
            content="this is not json",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 422


# ── GET /timer/{id} ──────────────────────────────────────────────────────────


class TestRetrieveTimer:
    """``GET /timer/{timer_id}`` — retrieve timer status."""

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
        body = resp.json()
        assert body["code"] == "TIMER_NOT_FOUND"

    @pytest.mark.parametrize(
        "scenario",
        _BAD_ID_CASES,
        ids=[c["id"] for c in _BAD_ID_CASES],
    )
    async def test_invalid_timer_id(self, client: AsyncClient, scenario: dict):
        resp = await client.get(
            scenario["path"],
            follow_redirects=False,
        )
        assert resp.status_code == scenario["expected_status"]


# ── Health ───────────────────────────────────────────────────────────────────


class TestHealth:
    """``GET /health`` — liveness probe."""

    async def test_root_redirects_to_docs(self, client: AsyncClient):
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/docs"

    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
