"""Read-only SMC/ICT analysis endpoint for Indian index and MCX candles."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from strategies.smc import analyze_guardeer, analyze_inner_circle, ict_killzone_status

router = APIRouter(tags=["SMC / ICT"])


class SmcAnalyzeRequest(BaseModel):
    instrument: str = Field(default="NIFTY", min_length=1, max_length=40)
    htf_candles: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    mtf_candles: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    ltf_candles: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    liquidity_tolerance: float | None = Field(default=None, gt=0)
    in_killzone: bool | None = None
    strategy_format: str = Field(default="Guardeer", pattern="^(Guardeer|Inner Circle)$")


@router.post("/v1/smc/analyze")
def smc_analyze(request: SmcAnalyzeRequest) -> dict[str, Any]:
    """Return explainable SMC evidence; never authorizes or places an order."""
    analyzer = analyze_guardeer if request.strategy_format == "Guardeer" else analyze_inner_circle
    killzone = ict_killzone_status()
    effective_killzone = killzone["active"] if request.in_killzone is None else request.in_killzone
    result = analyzer(
        request.htf_candles,
        request.mtf_candles,
        request.ltf_candles,
        instrument=request.instrument,
        liquidity_tolerance=request.liquidity_tolerance,
        in_killzone=effective_killzone,
    )
    result["killzone_status"] = {
        **killzone,
        "effective_active": effective_killzone,
        "manual_override": request.in_killzone is not None,
    }
    return result
