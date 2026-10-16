"""Parmar strategy-suite registry.

This is a fail-closed orchestration boundary for the seven requested strategies.
It deliberately does not fabricate market data or turn a detector into a trade.
A strategy is runnable only when its adapter is explicitly registered by the
backend with verified input schemas. Until then it returns WAIT with reasons.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    name: str
    engine_module: str | None
    status: str
    required_inputs: tuple[str, ...]
    notes: str


@dataclass
class StrategyResult:
    strategy_id: str
    name: str
    decision: str = "WAIT"
    candidate_decision: str | None = None
    entry: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    strike: float | None = None
    option_side: str | None = None
    reasons: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=lambda: ["PARMAR_ENGINE_FAIL_CLOSED"])
    live_validation: dict[str, Any] = field(default_factory=lambda: {
        "verdict": "FAIL", "decision": "WAIT", "blocks": ["Strategy adapter not registered"],
    })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


STRATEGIES: tuple[StrategyDefinition, ...] = (
    StrategyDefinition("oi_price_action", "Price Action / OI Price Action",
        "quant.oi_price_action_engine", "ENGINE_SOURCE_PRESENT",
        ("timestamped_ohlcv", "fresh_option_chain"), "OI and price-action confluence; stale inputs block."),
    StrategyDefinition("hero_zero", "Hero Zero",
        "quant.hero_zero", "ENGINE_SOURCE_PRESENT",
        ("verified_expiry", "timestamped_ohlcv", "fresh_option_quotes"), "Expiry-only, high-risk candidate; strict time and quote guards."),
    StrategyDefinition("failed_move_pdh_pdl", "Failed Move / PDH-PDL",
        "quant.failed_move_fade", "ENGINE_SOURCE_PRESENT",
        ("timestamped_ohlcv", "previous_day_high", "previous_day_low"), "Previous-day levels must be supplied, never inferred from current session."),
    StrategyDefinition("ema_crossover", "EMA Crossover",
        "quant.ema_quant_engine", "ENGINE_SOURCE_PRESENT",
        ("timestamped_ohlcv", "spot", "strike_step"), "EMA crossover is a candidate only; risk and freshness gates remain required."),
    StrategyDefinition("day_hl_liquidity_sweep", "Day HL Liquidity Sweep",
        "quant.day_hl_liquidity", "DETECTOR_SOURCE_PRESENT",
        ("timestamped_ohlcv", "previous_day_high", "previous_day_low"), "Sweep detector does not independently define entry, stop or target."),
    StrategyDefinition("orb", "Opening Range Breakout (ORB)",
        None, "ENGINE_NOT_IMPLEMENTED",
        ("timestamped_ohlcv", "session_open_window"), "Remain WAIT until a tested ORB engine is implemented."),
    StrategyDefinition("vwap", "VWAP Strategy",
        None, "ENGINE_NOT_IMPLEMENTED",
        ("timestamped_ohlcv", "volume"), "Remain WAIT until entry/exit rules and a tested VWAP engine are implemented."),
)

_ADAPTERS: dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] = {}


def register_adapter(strategy_id: str, adapter: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None:
    """Register a tested backend adapter. No implicit/default adapter is allowed."""
    known = {item.strategy_id for item in STRATEGIES}
    if strategy_id not in known:
        raise ValueError(f"Unknown Parmar strategy: {strategy_id}")
    if not callable(adapter):
        raise TypeError("adapter must be callable")
    _ADAPTERS[strategy_id] = adapter


def list_strategies() -> list[dict[str, Any]]:
    return [asdict(item) for item in STRATEGIES]


def evaluate_strategy(strategy_id: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a registered adapter; all missing/unverified paths safely return WAIT."""
    definition = next((item for item in STRATEGIES if item.strategy_id == strategy_id), None)
    if definition is None:
        return StrategyResult(
            strategy_id=str(strategy_id), name="Unknown strategy",
            reasons=["Unknown strategy id; no evaluation performed."],
            guards=["UNKNOWN_STRATEGY"],
            live_validation={"verdict": "FAIL", "decision": "WAIT",
                             "blocks": ["Unknown strategy id"]},
        ).to_dict()

    adapter = _ADAPTERS.get(strategy_id)
    if adapter is None:
        return StrategyResult(
            strategy_id=definition.strategy_id, name=definition.name,
            reasons=[definition.notes, "Backend adapter is not registered; no signal was generated."],
            guards=["ADAPTER_NOT_REGISTERED", "NO_ACTIONABLE_SIGNAL"],
            live_validation={"verdict": "FAIL", "decision": "WAIT",
                             "blocks": ["Backend adapter is not registered"]},
        ).to_dict()

    try:
        raw = adapter(inputs)
        if not isinstance(raw, Mapping):
            raise TypeError("Strategy adapter must return a mapping")
        result = dict(raw)
        # The orchestrator never upgrades a strategy result to an actionable decision.
        result["strategy_id"] = definition.strategy_id
        result["name"] = definition.name
        result["decision"] = "WAIT"
        if not result.get("candidate_decision"):
            result["candidate_decision"] = None
        guards = list(result.get("guards") or [])
        guards.extend(["PARMAR_DOWNSTREAM_VALIDATION_REQUIRED"])
        result["guards"] = list(dict.fromkeys(guards))
        validation = dict(result.get("live_validation") or {})
        validation["decision"] = "WAIT"
        validation["verdict"] = "FAIL"
        blocks = list(validation.get("blocks") or [])
        blocks.append("Parmar orchestrator requires downstream freshness, risk and 10-minute stability validation")
        validation["blocks"] = list(dict.fromkeys(blocks))
        result["live_validation"] = validation
        return result
    except Exception as exc:
        return StrategyResult(
            strategy_id=definition.strategy_id, name=definition.name,
            reasons=[f"Adapter failed safely: {type(exc).__name__}"],
            guards=["ADAPTER_ERROR", "NO_ACTIONABLE_SIGNAL"],
            live_validation={"verdict": "FAIL", "decision": "WAIT",
                             "blocks": ["Strategy adapter failed"]},
        ).to_dict()
