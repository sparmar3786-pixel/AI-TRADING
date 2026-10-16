"""Parmar strategy API: inventory plus fail-closed evaluation boundary.

This module intentionally does not fabricate market data or register unverified
strategy adapters. Existing broker, freshness, risk and stability checks remain
authoritative. Until an engine adapter is wired and tested, evaluation returns WAIT.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/parmar", tags=["Parmar strategy engine"])

STRATEGIES: tuple[dict[str, Any], ...] = (
    {"id": "oi_price_action", "name": "Price Action / OI Price Action", "source": "quant/oi_price_action_engine.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "hero_zero", "name": "Hero Zero", "source": "quant/hero_zero.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "failed_move_pdh_pdl", "name": "Failed Move / PDH-PDL", "source": "quant/failed_move_fade.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "ema_crossover", "name": "EMA Crossover", "source": "quant/ema_quant_engine.py", "status": "SOURCE_PRESENT_ADAPTER_PENDING"},
    {"id": "day_hl_liquidity_sweep", "name": "Day HL Liquidity Sweep", "source": "quant/day_hl_liquidity.py", "status": "DETECTOR_ADAPTER_PENDING"},
    {"id": "orb", "name": "Opening Range Breakout (ORB)", "source": None, "status": "ENGINE_NOT_IMPLEMENTED"},
    {"id": "vwap", "name": "VWAP Strategy", "source": None, "status": "ENGINE_NOT_IMPLEMENTED"},
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


@router.get("/strategies")
def list_parmar_strategies(x_device_id: str = Header(default="")) -> dict[str, Any]:
    _check_device(x_device_id)
    return {"status": "ok", "engine": "PARMAR", "count": len(STRATEGIES), "strategies": list(STRATEGIES)}


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
