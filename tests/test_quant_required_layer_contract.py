from backend.app.main import _live_validation_contract, _wait_signal


EXPECTED_STRATEGIES = {
    "oi_price_action",
    "hero_zero",
    "failed_move_pdh_pdl",
    "ema_crossover",
    "day_hl_liquidity_sweep",
    "orb",
    "vwap",
}


def test_wait_signal_keeps_strategy_tab_populated_without_live_data():
    payload = _wait_signal("NIFTY", "Angel One snapshot unavailable")

    assert payload["decision"] == "WAIT"
    assert payload["data_fresh"] is False
    assert set(payload["strategy_candidates"]) == EXPECTED_STRATEGIES
    for candidate in payload["strategy_candidates"].values():
        assert candidate["decision"] == "WAIT"
        assert candidate["candidate_decision"] is None
        assert candidate["actionable"] is False
        assert candidate["data_fresh"] is False
        assert candidate["entry"] is None
        assert candidate["stop_loss"] is None
        assert candidate["target"] is None
        assert candidate["strike"] is None
        assert candidate["guards"]


def test_quant_validation_requires_the_five_named_canonical_layers():
    unrelated_layers = {f"extra_{index}": {"pass": True} for index in range(5)}
    validation = _live_validation_contract(
        {"decision": "CALL BUY", "entry": 100.0, "stop_loss": 90.0, "target": 120.0},
        unrelated_layers,
        option_age_seconds=1.0,
    )
    assert validation["checks"]["five_layer_engine"] is False
    assert validation["verdict"] == "WAIT"
    assert validation["decision"] == "WAIT"
    assert "FIVE_LAYER_ENGINE" in validation["blocks"]


def test_quant_validation_uses_canonical_layers_even_with_extra_metadata():
    required = ("data_quality", "trend_sentiment", "order_flow", "option_selection", "risk_levels")
    layers = {key: {"pass": True} for key in required}
    layers["debug_metadata"] = {"pass": False}
    validation = _live_validation_contract(
        {"decision": "CALL BUY", "entry": 100.0, "stop_loss": 90.0, "target": 120.0},
        layers,
        option_age_seconds=1.0,
    )
    assert validation["checks"]["five_layer_engine"] is True
    # Independent freshness/option/risk gates still prevent a false PASS.
    assert validation["verdict"] == "WAIT"
