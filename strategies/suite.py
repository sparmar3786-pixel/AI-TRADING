"""Unified, fail-closed strategy suite for normalized OHLCV research data.

This module evaluates existing local strategy functions; it does not fetch data,
claim profitability, or place orders. Every strategy uses completed candles only.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from strategies.technical import atr, ema, ema_crossover, rsi_reversion, sma
from strategies.advanced import bollinger_reentry, donchian_breakout, macd, vwap
from risk.position_sizing import atr_stop_target


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _cross_signal(fast: list[float | None], slow: list[float | None]) -> list[str]:
    out: list[str] = []
    previous: str | None = None
    for a, b in zip(fast, slow):
        if a is None or b is None:
            out.append("WAIT")
            continue
        state = "LONG" if a > b else "SHORT" if a < b else "WAIT"
        out.append(state if state != previous else "WAIT")
        previous = state
    return out


def classify_oi_change(price_change: Any, oi_change: Any) -> str:
    """Classify price/OI direction without treating the classification as a trade."""
    price, oi = _number(price_change), _number(oi_change)
    if price is None or oi is None or price == 0 or oi == 0:
        return "UNKNOWN"
    if price > 0 and oi > 0:
        return "LONG_BUILDUP"
    if price < 0 and oi > 0:
        return "SHORT_BUILDUP"
    if price > 0 and oi < 0:
        return "SHORT_COVERING"
    return "LONG_UNWINDING"


def evaluate_strategy_suite(
    candles: list[dict[str, Any]],
    *,
    oi_change: Any = None,
    min_consensus: int = 3,
    risk_reward: float = 2.0,
) -> dict[str, Any]:
    """Evaluate technical, breakout, mean-reversion, VWAP and OI context.

    Input candle fields: high, low, close; volume is required for VWAP.
    Missing/invalid values fail closed. Returned levels are research estimates,
    not exchange-valid lot/option order instructions.
    """
    if min_consensus < 1:
        raise ValueError("min_consensus must be >= 1")
    if risk_reward <= 0 or not isfinite(float(risk_reward)):
        raise ValueError("risk_reward must be finite and > 0")
    if not isinstance(candles, list) or not candles:
        return {"status": "insufficient_data", "signal": "WAIT", "strategies": {}, "votes": {"LONG": 0, "SHORT": 0}, "risk_levels": None}

    normalized: list[dict[str, float]] = []
    for row in candles:
        if not isinstance(row, dict):
            return {"status": "invalid_data", "signal": "WAIT", "strategies": {}, "votes": {"LONG": 0, "SHORT": 0}, "risk_levels": None}
        vals = {key: _number(row.get(key)) for key in ("high", "low", "close", "volume")}
        if any(vals[k] is None for k in ("high", "low", "close")):
            return {"status": "invalid_data", "signal": "WAIT", "strategies": {}, "votes": {"LONG": 0, "SHORT": 0}, "risk_levels": None}
        high, low, close = vals["high"], vals["low"], vals["close"]
        if high is None or low is None or close is None or high < low or close <= 0:
            return {"status": "invalid_data", "signal": "WAIT", "strategies": {}, "votes": {"LONG": 0, "SHORT": 0}, "risk_levels": None}
        if vals["volume"] is not None and vals["volume"] < 0:
            return {"status": "invalid_data", "signal": "WAIT", "strategies": {}, "votes": {"LONG": 0, "SHORT": 0}, "risk_levels": None}
        normalized.append({k: v for k, v in vals.items() if v is not None})

    highs = [x["high"] for x in normalized]
    lows = [x["low"] for x in normalized]
    closes = [x["close"] for x in normalized]
    volumes = [x.get("volume", 0.0) for x in normalized]
    if len(closes) < 3:
        return {"status": "insufficient_data", "signal": "WAIT", "strategies": {}, "votes": {"LONG": 0, "SHORT": 0}, "risk_levels": None}

    signals: dict[str, str] = {}
    signals["sma_5_20"] = _cross_signal(sma(closes, 5), sma(closes, 20))[-1]
    signals["ema_9_21"] = ema_crossover(closes, 9, 21)[-1] if len(closes) >= 21 else "WAIT"
    signals["rsi_reversion"] = rsi_reversion(closes, 14)[-1] if len(closes) > 14 else "WAIT"
    signals["donchian_breakout"] = donchian_breakout(closes, highs, lows, 20)[-1] if len(closes) > 20 else "WAIT"
    signals["bollinger_reentry"] = bollinger_reentry(closes, 20)[-1] if len(closes) >= 20 else "WAIT"

    macd_result = macd(closes)
    hist = macd_result["histogram"]
    signals["macd_momentum"] = (
        "LONG" if len(hist) >= 2 and hist[-2] is not None and hist[-1] is not None and hist[-2] <= 0 < hist[-1]
        else "SHORT" if len(hist) >= 2 and hist[-2] is not None and hist[-1] is not None and hist[-2] >= 0 > hist[-1]
        else "WAIT"
    )
    if all("volume" in row for row in normalized):
        vwap_values = vwap(highs, lows, closes, volumes)
        signals["vwap_bias"] = "LONG" if vwap_values[-1] is not None and closes[-1] > vwap_values[-1] else "SHORT" if vwap_values[-1] is not None and closes[-1] < vwap_values[-1] else "WAIT"
    else:
        signals["vwap_bias"] = "WAIT"

    votes = {"LONG": sum(v == "LONG" for v in signals.values()), "SHORT": sum(v == "SHORT" for v in signals.values())}
    direction = "LONG" if votes["LONG"] >= min_consensus and votes["LONG"] > votes["SHORT"] else "SHORT" if votes["SHORT"] >= min_consensus and votes["SHORT"] > votes["LONG"] else "WAIT"
    atr_values = atr(highs, lows, closes, 14)
    atr_value = atr_values[-1] if atr_values else None
    risk_levels = None
    if direction in ("LONG", "SHORT") and atr_value is not None and atr_value > 0:
        risk_levels = atr_stop_target(closes[-1], atr_value, direction, stop_multiple=1.5, reward_risk=risk_reward)
    price_change = (closes[-1] / closes[-2] - 1.0) if len(closes) >= 2 else None
    oi_state = classify_oi_change(price_change, oi_change)
    return {
        "status": "ok",
        "signal": direction,
        "signal_semantics": "Rule-based research consensus; not a probability or live-order instruction",
        "strategies": signals,
        "votes": votes,
        "minimum_consensus": min_consensus,
        "latest_close": closes[-1],
        "atr_14": atr_value,
        "risk_levels": risk_levels,
        "oi_context": oi_state,
        "support_resistance": {"support": min(lows[-20:]), "resistance": max(highs[-20:]), "lookback_bars": min(20, len(closes))},
        "execution": "disabled",
    }
