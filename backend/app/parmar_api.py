"""Parmar strategy API: inventory plus fail-closed evaluation boundary.
The deployed branch also ships the quant source modules, but source presence is not live wiring.

This module intentionally does not fabricate market data or register unverified
strategy adapters. Existing broker, freshness, risk and stability checks remain
authoritative. Until an engine adapter is wired and tested, evaluation returns WAIT.
"""
from __future__ import annotations

from typing import Any
import importlib.util
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/parmar", tags=["Parmar strategy engine"])

STRATEGIES: tuple[dict[str, Any], ...] = (
    {"id": "oi_price_action", "name": "Price Action / OI Price Action", "source": "quant/oi_price_action_engine.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "hero_zero", "name": "Hero Zero", "source": "quant/hero_zero.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "failed_move_pdh_pdl", "name": "Failed Move / PDH-PDL", "source": "quant/failed_move_fade.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "ema_crossover", "name": "EMA Crossover", "source": "quant/ema_quant_engine.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "day_hl_liquidity_sweep", "name": "Day HL Liquidity Sweep", "source": "quant/day_hl_liquidity.py", "status": "DETECTOR_ADAPTER_PENDING"},
    {"id": "orb", "name": "Opening Range Breakout (ORB)", "source": "quant/orb_engine.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "vwap", "name": "VWAP Strategy", "source": "quant/vwap_strategy.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
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
    "orb": ("quant.orb_engine", "SOURCE_ONLY"),
    "vwap": ("quant.vwap_strategy", "SOURCE_ONLY"),
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
        item["status"] = source_status if available else ("ENGINE_SOURCE_MISSING_IN_DEPLOYMENT" if module_name else "NOT_IMPLEMENTED")
        item["live_api_wiring"] = "NOT_VERIFIED"
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
    checks = {
        "backend_route_registered": True,
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
        "live_api_wiring": "NOT_VERIFIED",
        "actionable": False,
        "checks": checks,
        "blockers": blockers,
        "reason": "Diagnostic route and module presence do not prove fresh live feed, risk mapping, or end-to-end wiring.",
    }


@router.post("/evaluate")
def evaluate_parmar_strategy(body: EvaluateRequest, x_device_id: str = Header(default="")) -> dict[str, Any]:
    _check_device(x_device_id)
    strategy_id = body.strategy_id.strip().lower()
    definition = next((item for item in STRATEGIES if item["id"] == strategy_id), None)
    if definition is None:
        raise HTTPException(status_code=404, detail="Unknown Parmar strategy id")
    # No implicit adapter, no signal synthesis from caller JSON. This is safe
    # until each real engine is explicitly connected to timestamped backend data.
    return {
        "status": "wait",
        "engine": "PARMAR",
        "strategy_id": strategy_id,
        "name": definition["name"],
        "decision": "WAIT",
        "candidate_decision": None,
        "entry": None,
        "stop_loss": None,
        "target": None,
        "strike": None,
        "reasons": ["Engine adapter and verified live-data mapping are not yet registered."],
        "guards": ["ADAPTER_NOT_REGISTERED", "NO_ACTIONABLE_SIGNAL"],
        "live_validation": {
            "verdict": "FAIL",
            "decision": "WAIT",
            "blocks": ["Adapter pending", "Freshness, risk and 10-minute stability gates required"],
        },
    }
