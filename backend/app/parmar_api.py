"""Parmar strategy API: inventory plus fail-closed evaluation boundary.
The deployed branch also ships the quant source modules, but source presence is not live wiring.

This module intentionally does not fabricate market data or register unverified
strategy adapters. Existing broker, freshness, risk and stability checks remain
authoritative. Until an engine adapter is wired and tested, evaluation returns WAIT.
"""
from __future__ import annotations

from typing import Any
import importlib.util
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

try:
    from app.api_auth import require_authenticated_device
except ModuleNotFoundError:
    from backend.app.api_auth import require_authenticated_device

router = APIRouter(prefix="/v1/parmar", tags=["Parmar strategy engine"], dependencies=[Depends(require_authenticated_device)])

STRATEGIES: tuple[dict[str, Any], ...] = (
    {"id": "oi_price_action", "name": "Price Action / OI Price Action", "source": "quant/oi_price_action_engine.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "hero_zero", "name": "Hero Zero", "source": "quant/hero_zero.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "failed_move_pdh_pdl", "name": "Failed Move / PDH-PDL", "source": "quant/failed_move_fade.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "ema_crossover", "name": "EMA Crossover", "source": "quant/ema_quant_engine.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "day_hl_liquidity_sweep", "name": "Day HL Liquidity Sweep", "source": "quant/day_hl_liquidity.py", "status": "DETECTOR_ADAPTER_PENDING"},
    {"id": "orb", "name": "Opening Range Breakout (ORB)", "source": "quant/orb_engine.py", "status": "CANDIDATE_PIPELINE_WIRED_WAIT_GATED"},
    {"id": "vwap", "name": "VWAP Strategy", "source": "quant/vwap_strategy.py", "status": "CANDIDATE_PIPELINE_WIRED_WAIT_GATED"},
)
_IDS = {item["id"] for item in STRATEGIES}


def _check_device(x_device_id: str) -> None:
    # Match the existing API's device identifier contract without weakening it.
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", x_device_id or ""):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Device-Id")


class EvaluateRequest(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=80)
    index: str = Field(default="NIFTY", min_length=1, max_length=24)
    # Explicitly caller-supplied data is not treated as live unless the upstream
    # backend later verifies its source timestamps and broker provenance.
    market_snapshot: dict[str, Any] = Field(default_factory=dict)


_ENGINE_MODULES = {
    "oi_price_action": ("quant.oi_price_action_engine", "SOURCE_ONLY"),
    "hero_zero": ("quant.hero_zero", "SOURCE_ONLY"),
    "failed_move_pdh_pdl": ("quant.failed_move_fade", "SOURCE_ONLY"),
    "ema_crossover": ("quant.ema_quant_engine", "SOURCE_ONLY"),
    "day_hl_liquidity_sweep": ("quant.day_hl_liquidity", "DETECTOR_ONLY"),
    "orb": ("quant.orb_engine", "CANDIDATE_PIPELINE_WIRED_WAIT_GATED"),
    "vwap": ("quant.vwap_strategy", "CANDIDATE_PIPELINE_WIRED_WAIT_GATED"),
}


def _module_available(module_name: str | None) -> bool:
    if not module_name:
        return False
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


@router.get("/strategies")
def list_parmar_strategies(x_device_id: str = Header(default="")) -> dict[str, Any]:
    _check_device(x_device_id)
    strategies = []
    for definition in STRATEGIES:
        item = dict(definition)
        module_name, source_status = _ENGINE_MODULES[item["id"]]
        available = _module_available(module_name)
        item["engine_module"] = module_name
        item["engine_loaded"] = available
        candidate_ids = {"oi_price_action", "hero_zero", "failed_move_pdh_pdl", "ema_crossover", "orb", "vwap"}
        detector_ids = {"day_hl_liquidity_sweep"}
        candidate_wired = item["id"] in candidate_ids
        detector_wired = item["id"] in detector_ids
        if not available:
            item["status"] = "ENGINE_SOURCE_MISSING_IN_DEPLOYMENT" if module_name else "NOT_IMPLEMENTED"
        elif candidate_wired:
            item["status"] = "CANDIDATE_PIPELINE_WIRED_WAIT_GATED"
        elif detector_wired:
            item["status"] = "DETECTOR_PIPELINE_WIRED_WAIT_GATED"
        else:
            item["status"] = source_status
        item["live_api_wiring"] = (
            "CANDIDATE_PIPELINE_WIRED; ACTIONABILITY_NOT_VERIFIED" if candidate_wired
            else "DETECTOR_PIPELINE_WIRED; ACTIONABILITY_NOT_VERIFIED" if detector_wired
            else "NOT_VERIFIED"
        )
        if candidate_wired or detector_wired:
            item["candidate_route"] = f"/v1/signals.strategy_candidates.{item['id']}"
        item["actionable"] = False
        strategies.append(item)
    return {"status": "ok", "engine": "PARMAR", "count": len(strategies), "strategies": strategies}


@router.post("/strategies/{strategy_id}/verify-wiring")
def verify_strategy_wiring(strategy_id: str, x_device_id: str = Header(default="")) -> dict[str, Any]:
    """Report verifiable wiring facts without treating route health as live readiness.

    This is intentionally a diagnostic-only dry run: it never calls the broker
    to place an order and never promotes a strategy based on source presence.
    """
    _check_device(x_device_id)
    strategy_id = strategy_id.strip().lower()
    definition = next((item for item in STRATEGIES if item["id"] == strategy_id), None)
    if definition is None:
        raise HTTPException(status_code=404, detail="Unknown Parmar strategy id")
    module_name, _ = _ENGINE_MODULES[strategy_id]
    engine_loaded = _module_available(module_name)
    candidate_ids = {"oi_price_action", "hero_zero", "failed_move_pdh_pdl", "ema_crossover", "orb", "vwap"}
    detector_ids = {"day_hl_liquidity_sweep"}
    candidate_pipeline_wired = strategy_id in candidate_ids and engine_loaded
    detector_pipeline_wired = strategy_id in detector_ids and engine_loaded
    checks = {
        "backend_route_registered": True,
        "candidate_pipeline_wired": candidate_pipeline_wired or detector_pipeline_wired,
        "engine_module_available": engine_loaded,
        "fresh_live_market_data": False,
        "signal_contract_validated": False,
        "risk_gate_verified": False,
        "broker_instrument_resolved": False,
        "paper_payload_constructed": False,
        "live_feed_received": False,
        "audit_written": False,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "strategy_id": strategy_id,
        "status": "WAIT",
        "live_api_wiring": (
            "CANDIDATE_PIPELINE_WIRED; ACTIONABILITY_NOT_VERIFIED" if candidate_pipeline_wired
            else "DETECTOR_PIPELINE_WIRED; ACTIONABILITY_NOT_VERIFIED" if detector_pipeline_wired
            else "NOT_VERIFIED"
        ),
        "actionable": False,
        "checks": checks,
        "blockers": blockers,
        "candidate_route": (
            f"/v1/signals.strategy_candidates.{strategy_id}"
            if candidate_pipeline_wired or detector_pipeline_wired else None
        ),
        "reason": (
            "Candidate calculation is connected to the server-owned /v1/signals payload, but fresh live feed, option mapping, five-layer validation, risk and 600-second confirmation are not certified."
            if candidate_pipeline_wired else
            "DAY-HL reports sweep evidence only; it is not a complete trade planner and remains WAIT-gated."
            if detector_pipeline_wired else
            "Diagnostic route and module presence do not prove fresh live feed, risk mapping, or end-to-end wiring."
        ),
    }


@router.post("/evaluate")
def evaluate_parmar_strategy(body: EvaluateRequest, x_device_id: str = Header(default="")) -> dict[str, Any]:
    _check_device(x_device_id)
    strategy_id = body.strategy_id.strip().lower()
    definition = next((item for item in STRATEGIES if item["id"] == strategy_id), None)
    if definition is None:
        raise HTTPException(status_code=404, detail="Unknown Parmar strategy id")
    # Ignore caller-supplied market_snapshot. Reuse the canonical server-owned
    # Angel One signal snapshot so Strategy, Signals and Quant tabs cannot diverge.
    try:
        try:
            from app.main import _get_signals
        except ModuleNotFoundError:
            from backend.app.main import _get_signals
        canonical = _get_signals()
    except Exception:
        canonical = {}
    index = body.index.strip().upper()
    signal = (canonical.get("signals") or {}).get(index) if isinstance(canonical, dict) else None
    if not isinstance(signal, dict):
        raise HTTPException(status_code=400, detail="Unsupported index or canonical signal snapshot unavailable")
    candidates = signal.get("strategy_candidates")
    candidate = candidates.get(strategy_id) if isinstance(candidates, dict) else None
    if not isinstance(candidate, dict):
        candidate = {
            "strategy_id": strategy_id, "decision": "WAIT", "candidate_decision": None,
            "entry": None, "stop_loss": None, "target": None, "strike": None,
            "entry_price_basis": "UNDERLYING_SPOT", "data_fresh": False,
            "reasons": ["Canonical strategy candidate is unavailable; retry after signal refresh."],
            "guards": ["STRATEGY_CANDIDATE_UNAVAILABLE", "NO_ACTIONABLE_SIGNAL"],
        }
    layers = signal.get("layers") if isinstance(signal.get("layers"), dict) else {}
    required_layers = ("data_quality", "trend_sentiment", "order_flow", "option_selection", "risk_levels")
    quant_pass = all(
        isinstance(layers.get(key), dict) and layers[key].get("pass") is True
        for key in required_layers
    )
    validation = signal.get("live_validation") if isinstance(signal.get("live_validation"), dict) else {}
    candidate_decision = str(candidate.get("candidate_decision") or "").upper()
    if candidate_decision not in {"CALL BUY", "PUT BUY"}:
        candidate_decision = None
    return {
        "status": "wait", "engine": "PARMAR", "strategy_id": strategy_id,
        "name": definition["name"], "index": index,
        "decision": "WAIT", "candidate_decision": candidate_decision,
        # Executable trade fields remain empty. Candidate levels below are spot-based research evidence.
        "entry": None, "stop_loss": None, "target": None, "strike": None,
        "candidate_snapshot": {
            "candidate_decision": candidate_decision,
            "entry": candidate.get("entry"), "stop_loss": candidate.get("stop_loss"),
            "target": candidate.get("target"),
            "entry_price_basis": candidate.get("entry_price_basis") or "UNDERLYING_SPOT",
            "timestamp": candidate.get("timestamp") or signal.get("generated_at"),
            "data_fresh": candidate.get("data_fresh") is True,
            "reasons": list(candidate.get("reasons") or []),
            "guards": list(candidate.get("guards") or []),
            "strategy_fields": {
                key: candidate.get(key)
                for key in ("opening_range_high", "opening_range_low", "vwap", "atr_value", "pdh", "pdl", "sweep_events")
                if key in candidate
            },
        },
        "checks": {
            "canonical_signal_found": True,
            "fresh_live_market_data": signal.get("data_fresh") is True,
            "five_layer_quant_pass": quant_pass,
            "risk_gate_pass": (validation.get("checks") or {}).get("risk_checks") is True,
            "ten_minute_confirmation": (signal.get("signal_stability") or {}).get("state") == "CONFIRMED",
            "order_placement_enabled": False,
        },
        "reasons": list(candidate.get("reasons") or []) + [
            "Candidate is informational only; option contract and risk mapping are not certified."
        ],
        "guards": list(dict.fromkeys(list(candidate.get("guards") or []) + [
            "OPTION_CONTRACT_MAPPING_REQUIRED", "FIVE_LAYER_QUANT_GATE_REQUIRED",
            "SERVER_600_SECOND_CONFIRMATION_REQUIRED", "NO_ACTIONABLE_SIGNAL",
        ])),
        "live_validation": {
            "verdict": "WAIT", "decision": "WAIT",
            "blocks": ["Executable option mapping/risk not certified", "Freshness, five-layer validation and 600-second stability gates must pass"],
            "order_placement_enabled": False,
        },
        "order_placement_enabled": False,
    }
