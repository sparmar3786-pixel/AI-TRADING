from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import smc_api


def test_smc_endpoint_accepts_profile_tolerance_and_defaults_to_real_killzone():
    client = TestClient(app)
    killzone = {
        "active": False,
        "window": None,
        "timezone": "America/New_York",
        "local_time": "2026-10-13T14:00:00-04:00",
    }
    with patch.object(smc_api, "ict_killzone_status", return_value=killzone):
        response = client.post("/v1/smc/analyze", json={
            "instrument": "NIFTY",
            "strategy_format": "Guardeer",
            "htf_candles": [],
            "mtf_candles": [],
            "ltf_candles": [],
            "liquidity_tolerance": 1.25,
        })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strategy_format"] == "Guardeer"
    assert body["liquidity_tolerance"] == 1.25
    assert body["in_killzone"] is False
    assert body["killzone_status"]["effective_active"] is False
    assert body["execution_allowed"] is False


def test_smc_endpoint_accepts_inner_circle_without_manual_killzone_override():
    client = TestClient(app)
    killzone = {
        "active": True,
        "window": "NEW_YORK_AM",
        "timezone": "America/New_York",
        "local_time": "2026-10-13T08:00:00-04:00",
    }
    with patch.object(smc_api, "ict_killzone_status", return_value=killzone):
        response = client.post("/v1/smc/analyze", json={
            "instrument": "BANKNIFTY",
            "strategy_format": "Inner Circle",
            "htf_candles": [],
            "mtf_candles": [],
            "ltf_candles": [],
        })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strategy_format"] == "Inner Circle"
    assert body["in_killzone"] is True
    assert body["killzone_status"]["window"] == "NEW_YORK_AM"
    assert body["execution_allowed"] is False
