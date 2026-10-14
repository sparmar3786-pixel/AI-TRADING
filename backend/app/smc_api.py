"""Read-only SMC/ICT analysis endpoint for Indian index and MCX candles."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Header, HTTPException, Query
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


@router.get("/v1/market/candles")
def market_candles(
    index: str = "NIFTY",
    interval: str = "FIVE_MINUTE",
    days: int = Query(default=3, ge=1, le=7),
    exchange: str | None = None,
    symboltoken: str | None = None,
    x_device_id: str = Header(default="", alias="X-Device-Id"),
) -> dict[str, Any]:
    """Read validated historical OHLCV candles from Angel One; never synthesize bars."""
    # Lazy import avoids a circular import while main.py includes this router.
    from app import main as api

    api._device(x_device_id)
    instrument = index.strip().upper()
    candle_interval = interval.strip().upper()
    allowed = {"ONE_MINUTE", "FIVE_MINUTE", "FIFTEEN_MINUTE", "ONE_HOUR", "ONE_DAY"}
    if candle_interval not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported candle interval.")

    if symboltoken:
        resolved_exchange = (exchange or "NSE").strip().upper()
        token = symboltoken.strip()
    else:
        config = api.INDEXES.get(instrument)
        if config is None:
            raise HTTPException(status_code=400, detail=f"Unsupported index: {instrument}")
        resolved_exchange = (exchange or config["exchange"]).strip().upper()
        token = config["token"]

    end_dt = datetime.now(api.IST).replace(second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=days)
    start_text = start_dt.strftime("%Y-%m-%d %H:%M")
    end_text = end_dt.strftime("%Y-%m-%d %H:%M")
    adapter = api._require_adapter()
    try:
        response = adapter.candles(resolved_exchange, token, candle_interval, start_text, end_text)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Angel One historical candle request failed; no synthetic candles were used.",
        ) from exc

    raw_rows = response.get("candles") if isinstance(response, dict) else None
    valid: list[dict[str, Any]] = []
    for row in raw_rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 6 or not row[0]:
            continue
        values = [api._number(row[i]) for i in range(1, 5)]
        if any(value is None for value in values):
            continue
        open_price, high, low, close = (float(value) for value in values)
        if high < max(open_price, close, low) or low > min(open_price, close, high):
            continue
        volume_value = api._number(row[5])
        valid.append({
            "timestamp": str(row[0]),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": max(0.0, float(volume_value or 0.0)),
        })
    valid.sort(key=lambda candle: candle["timestamp"])
    return {
        "status": "ok" if valid else "no_candles",
        "source": "angelone_smartapi_historical_candles",
        "index": instrument,
        "exchange": resolved_exchange,
        "symboltoken": token,
        "interval": candle_interval,
        "history_days": days,
        "live": False,
        "count": len(valid),
        "first_candle": valid[0]["timestamp"] if valid else None,
        "last_candle": valid[-1]["timestamp"] if valid else None,
        "source_timestamp": valid[-1]["timestamp"] if valid else None,
        "generated_at": datetime.now(api.IST).isoformat(),
        "candles": valid,
    }
