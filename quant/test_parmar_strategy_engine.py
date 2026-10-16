"""Regression tests for the fail-closed Parmar strategy registry."""
from quant.parmar_strategy_engine import STRATEGIES, evaluate_strategy, register_adapter


def test_all_seven_requested_strategies_are_registered():
    names = {item.name for item in STRATEGIES}
    assert names == {
        "Price Action / OI Price Action",
        "Hero Zero",
        "Failed Move / PDH-PDL",
        "EMA Crossover",
        "Day HL Liquidity Sweep",
        "Opening Range Breakout (ORB)",
        "VWAP Strategy",
    }


def test_unregistered_strategy_adapter_fails_closed():
    for strategy in STRATEGIES:
        result = evaluate_strategy(strategy.strategy_id, {})
        assert result["decision"] == "WAIT"
        assert result["live_validation"]["verdict"] == "FAIL"
        assert result["live_validation"]["decision"] == "WAIT"
        assert result["entry"] is None
        assert result["stop_loss"] is None
        assert result["target"] is None


def test_registered_adapter_cannot_promote_decision():
    register_adapter("ema_crossover", lambda _: {
        "decision": "CALL BUY",
        "candidate_decision": "CALL BUY",
        "entry": 100.0,
        "stop_loss": 95.0,
        "target": 110.0,
        "live_validation": {"verdict": "PASS", "decision": "CALL BUY", "blocks": []},
    })
    result = evaluate_strategy("ema_crossover", {"market_data": "test"})
    assert result["decision"] == "WAIT"
    assert result["candidate_decision"] == "CALL BUY"
    assert result["live_validation"]["verdict"] == "FAIL"
    assert result["live_validation"]["decision"] == "WAIT"
    assert "PARMAR_DOWNSTREAM_VALIDATION_REQUIRED" in result["guards"]


def test_unknown_strategy_fails_closed():
    result = evaluate_strategy("unknown", {})
    assert result["decision"] == "WAIT"
    assert result["live_validation"]["verdict"] == "FAIL"
