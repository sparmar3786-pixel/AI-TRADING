import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app, _complete_strategy_candidate_inventory
import app.main as backend_main


DEVICE_HEADERS = {"X-Device-Id": "A" * 43}


def test_parmar_strategy_inventory_is_backend_computed_and_non_actionable():
    client = TestClient(app)
    response = client.get("/v1/parmar/strategies", headers=DEVICE_HEADERS)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["engine"] == "PARMAR"
    assert payload["count"] >= 7
    ids = {strategy["id"] for strategy in payload["strategies"]}
    assert {
        "oi_price_action",
        "hero_zero",
        "failed_move_pdh_pdl",
        "ema_crossover",
        "day_hl_liquidity_sweep",
        "orb",
        "vwap",
    } <= ids
    for strategy in payload["strategies"]:
        assert strategy["actionable"] is False
        if strategy["id"] in {"oi_price_action", "hero_zero", "failed_move_pdh_pdl", "ema_crossover", "orb", "vwap"}:
            # Candidate evaluation is wired to the server-owned signal payload,
            # but contract/risk/stability gates still prohibit actionability.
            assert strategy["status"] == "CANDIDATE_PIPELINE_WIRED_WAIT_GATED"
            assert strategy["live_api_wiring"] == "CANDIDATE_PIPELINE_WIRED; ACTIONABILITY_NOT_VERIFIED"
            assert strategy["candidate_route"]
        elif strategy["id"] == "day_hl_liquidity_sweep":
            assert strategy["status"] == "DETECTOR_PIPELINE_WIRED_WAIT_GATED"
            assert strategy["live_api_wiring"] == "DETECTOR_PIPELINE_WIRED; ACTIONABILITY_NOT_VERIFIED"
        else:
            assert strategy["live_api_wiring"] == "NOT_VERIFIED"


def test_verify_wiring_never_promotes_from_route_or_source_presence():
    client = TestClient(app)
    response = client.post(
        "/v1/parmar/strategies/ema_crossover/verify-wiring",
        headers=DEVICE_HEADERS,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "WAIT"
    assert result["live_api_wiring"] == "CANDIDATE_PIPELINE_WIRED; ACTIONABILITY_NOT_VERIFIED"
    assert result["actionable"] is False
    assert result["checks"]["backend_route_registered"] is True
    assert result["checks"]["fresh_live_market_data"] is False
    assert result["checks"]["risk_gate_verified"] is False
    assert result["checks"]["live_feed_received"] is False
    assert result["blockers"]



def test_verify_wiring_reports_hero_zero_candidate_pipeline_but_keeps_it_wait_gated():
    client = TestClient(app)
    response = client.post(
        "/v1/parmar/strategies/hero_zero/verify-wiring",
        headers=DEVICE_HEADERS,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "WAIT"
    assert result["live_api_wiring"] == "CANDIDATE_PIPELINE_WIRED; ACTIONABILITY_NOT_VERIFIED"
    assert result["candidate_route"] == "/v1/signals.hero_zero"
    assert result["checks"]["candidate_pipeline_wired"] is True
    assert result["checks"]["fresh_live_market_data"] is False
    assert result["checks"]["risk_gate_verified"] is False
    assert result["actionable"] is False
    assert result["blockers"]


def test_direct_evaluate_never_trusts_caller_snapshot_or_emits_trade_levels():
    client = TestClient(app)
    response = client.post(
        "/v1/parmar/evaluate",
        headers=DEVICE_HEADERS,
        json={
            "strategy_id": "hero_zero",
            "index": "NIFTY",
            "market_snapshot": {
                "observed_at": "2026-10-16T10:00:00+05:30",
                "underlying_ltp": 25000,
                "option_chain": [{"strike": 25000, "ltp": 1.0}],
            },
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == "WAIT"
    assert result["entry"] is None
    assert result["stop_loss"] is None
    assert result["target"] is None
    assert result["strike"] is None
    assert result["live_validation"]["decision"] == "WAIT"
    assert "ADAPTER_NOT_REGISTERED" in result["guards"]


def test_verify_wiring_rejects_unknown_strategy_and_invalid_device():
    client = TestClient(app)
    unknown = client.post(
        "/v1/parmar/strategies/not-a-strategy/verify-wiring",
        headers=DEVICE_HEADERS,
    )
    assert unknown.status_code == 404
    unauthenticated = client.get("/v1/parmar/strategies")
    assert unauthenticated.status_code == 401



def test_candidate_inventory_preserves_successful_results_and_fills_missing_engines():
    successful = {
        "orb": {"strategy_id": "orb", "decision": "WAIT", "actionable": False, "reasons": ["no setup"]},
        "ema_crossover": {"strategy_id": "ema_crossover", "decision": "WAIT", "actionable": False},
    }
    result = _complete_strategy_candidate_inventory(successful, "injected engine failure")
    assert set(result) == {
        "oi_price_action", "hero_zero", "failed_move_pdh_pdl", "ema_crossover",
        "day_hl_liquidity_sweep", "orb", "vwap",
    }
    assert result["orb"]["reasons"] == ["no setup"]
    assert result["ema_crossover"]["decision"] == "WAIT"
    for strategy_id in {"oi_price_action", "hero_zero", "failed_move_pdh_pdl", "day_hl_liquidity_sweep", "vwap"}:
        row = result[strategy_id]
        assert row["decision"] == "WAIT"
        assert row["actionable"] is False
        assert row["data_fresh"] is False
        assert row["entry"] is None
        assert row["stop_loss"] is None
        assert row["target"] is None
        assert row["strike"] is None
        assert "ENGINE_EVALUATION_INCOMPLETE" in row["guards"]


def test_signals_endpoint_returns_fail_closed_wait_payload_on_unexpected_collector_error(monkeypatch):
    client = TestClient(app)
    def fail_collection():
        raise RuntimeError("synthetic test failure")
    monkeypatch.setattr(backend_main, "_get_signals", fail_collection)
    response = client.get("/v1/signals", headers=DEVICE_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    assert payload["live"] is False
    assert "failed safely" in payload["message"].lower()
    assert payload["trade_plans"] == []
    assert payload["qualified_trade_count"] == 0
