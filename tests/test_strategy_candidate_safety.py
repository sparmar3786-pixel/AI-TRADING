import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import _gate_strategy_candidate_payload


def test_stale_strategy_candidate_clears_all_trade_levels_and_contract_fields():
    payload = {
        "candidate_decision": "CALL BUY",
        "option_side": "CE",
        "strike": 25000,
        "expiry": "2026-10-22",
        "entry": 25010,
        "stop_loss": 24980,
        "target": 25070,
        "risk_reward": "2:1",
        "contract_symbol": "NIFTY26OCT25000CE",
        "data_fresh": True,
        "guards": [],
    }

    result = _gate_strategy_candidate_payload(
        payload, source_fresh=False, strategy_id="ema_crossover"
    )

    assert result["decision"] == "WAIT"
    assert result["actionable"] is False
    assert result["candidate_decision"] is None
    for field in ("strike", "expiry", "option_side", "entry", "stop_loss", "target", "risk_reward", "contract_symbol"):
        assert result[field] is None
    assert "STALE_OR_INCOMPLETE_SOURCE_DATA" in result["guards"]


def test_wait_without_candidate_cannot_leak_old_levels():
    payload = {
        "candidate_decision": None,
        "strike": 25000,
        "entry": 25010,
        "stop_loss": 24980,
        "target": 25070,
        "data_fresh": True,
        "guards": [],
    }

    result = _gate_strategy_candidate_payload(
        payload, source_fresh=True, strategy_id="oi_price_action"
    )

    assert result["decision"] == "WAIT"
    assert result["actionable"] is False
    assert result["candidate_decision"] is None
    for field in ("strike", "expiry", "option_side", "entry", "stop_loss", "target", "risk_reward", "contract_symbol"):
        assert result.get(field) is None
    assert "NO_VALID_STRATEGY_CANDIDATE" in result["guards"]


def test_valid_spot_candidate_remains_non_actionable_until_live_gates_pass():
    payload = {
        "candidate_decision": "PUT BUY",
        "option_side": "PE",
        "strike": 24950,
        "entry": 24900,
        "stop_loss": 24950,
        "target": 24800,
        "data_fresh": True,
        "guards": [],
    }

    result = _gate_strategy_candidate_payload(
        payload, source_fresh=True, strategy_id="failed_move_pdh_pdl"
    )

    assert result["decision"] == "WAIT"
    assert result["actionable"] is False
    assert result["candidate_decision"] == "PUT BUY"
    assert result["entry_price_basis"] == "UNDERLYING_SPOT"
    assert result["entry"] == 24900
    assert result["stop_loss"] == 24950
    assert result["target"] == 24800
