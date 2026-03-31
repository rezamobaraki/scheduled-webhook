"""Unit tests for Pydantic request/response schemas.

No database or external services required — runs instantly.
"""

import json
import uuid
from pathlib import Path

import pytest

from src.schemas import TimerCreateRequest, TimerCreateResponse, TimerRetrieveResponse

# ── Load test scenarios from JSON seeder ─────────────────────────────────────

_SCENARIOS_PATH = Path(__file__).parents[1] / "data" / "timer_scenarios.json"
_SCENARIOS = json.loads(_SCENARIOS_PATH.read_text())

_VALID_CASES = _SCENARIOS["create_timer"]["valid"]
_INVALID_CASES = _SCENARIOS["create_timer"]["invalid"]


class TestTimerCreateRequest:
    """Validate ``TimerCreateRequest`` schema parsing and constraints."""

    @pytest.mark.parametrize(
        "scenario",
        _VALID_CASES,
        ids=[c["id"] for c in _VALID_CASES],
    )
    def test_valid_payload_parses(self, scenario: dict):
        req = TimerCreateRequest(**scenario["payload"])
        assert req.total_seconds == scenario["expected_time_left"]

    @pytest.mark.parametrize(
        "scenario",
        [c for c in _INVALID_CASES if c["payload"] is not None],
        ids=[c["id"] for c in _INVALID_CASES if c["payload"] is not None],
    )
    def test_invalid_payload_raises(self, scenario: dict):
        with pytest.raises(Exception):  # noqa: B017 — ValidationError or ValueError
            TimerCreateRequest(**scenario["payload"])

    def test_total_seconds_property(self):
        req = TimerCreateRequest(
            hours=1, minutes=30, seconds=45, url="https://example.com",
        )
        assert req.total_seconds == 5445


class TestTimerCreateResponse:
    """Validate ``TimerCreateResponse`` schema."""

    def test_serialises_uuid_and_time_left(self):
        timer_id = uuid.uuid4()
        resp = TimerCreateResponse(id=timer_id, time_left=120)
        assert resp.id == timer_id
        assert resp.time_left == 120


class TestTimerRetrieveResponse:
    """Validate ``TimerRetrieveResponse`` schema."""

    def test_serialises_uuid_and_time_left(self):
        timer_id = uuid.uuid4()
        resp = TimerRetrieveResponse(id=timer_id, time_left=0)
        assert resp.id == timer_id
        assert resp.time_left == 0

