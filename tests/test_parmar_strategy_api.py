import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app


def test_parmar_strategy_inventory_is_backend_computed_and_non_actionable():
    client = TestClient(app)
    response = client.get("/v1/parmar/strategies", headers={"X-Device-Id": "A" * 43})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["engine"] == "PARMAR"
    assert payload["count"] >= 5
    for strategy in payload["strategies"]:
        assert strategy["live_api_wiring"] == "NOT_VERIFIED"
        assert strategy["actionable"] is False
        if strategy["id"] in {"orb", "vwap"}:
            assert strategy["status"] == "NOT_IMPLEMENTED"


def test_verify_wiring_never_promotes_from_route_or_source_presence():
    client = TestClient(app)
    response = client.post(
        "/v1/parmar/strategies/ema_crossover/verify-wiring",
        headers={"X-Device-Id": "A" * 43},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "WAIT"
    assert result["live_api_wiring"] == "NOT_VERIFIED"
    assert result["actionable"] is False
    assert result["checks"]["backend_route_registered"] is True
    assert result["checks"]["fresh_live_market_data"] is False
    assert result["checks"]["risk_gate_verified"] is False
    assert result["checks"]["live_feed_received"] is False
    assert result["blockers"]


def test_verify_wiring_rejects_unknown_strategy_and_invalid_device():
    client = TestClient(app)
    unknown = client.post(
        "/v1/parmar/strategies/not-a-strategy/verify-wiring",
        headers={"X-Device-Id": "A" * 43},
    )
    assert unknown.status_code == 404
    unauthenticated = client.get("/v1/parmar/strategies")
    assert unauthenticated.status_code == 401
