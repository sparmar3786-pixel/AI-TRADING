"""Deterministic previous-day high/low liquidity sweep detection.

This module deliberately requires previous-session levels and ordered OHLC bars.
It does not infer PDH/PDL from the current session's high/low or manufacture data.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from math import isfinite
from typing import Iterable, Mapping, Any


@dataclass(frozen=True)
class LiquiditySweep:
    side: str
    level_name: str
    level: float
    candle_time: str
    candle_high: float
    candle_low: float
    candle_close: float
    confirmation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not isfinite(result) or result <= 0:
        raise ValueError(f"{field} must be a finite positive number")
    return result


def detect_pdh_pdl_sweeps(
    candles: Iterable[Mapping[str, Any]],
    previous_day_high: float,
    previous_day_low: float,
) -> list[LiquiditySweep]:
    """Detect wick-through-and-close-back sweeps in chronological OHLC candles.

    A PDH sweep is bearish when high > PDH and close < PDH.
    A PDL sweep is bullish when low < PDL and close > PDL.
    Candles that only touch a level are not sweeps. Results are returned in
    candle order; if one candle sweeps both levels, both events are reported.
    """
    pdh = _number(previous_day_high, "previous_day_high")
    pdl = _number(previous_day_low, "previous_day_low")
    if pdh < pdl:
        raise ValueError("previous_day_high must be >= previous_day_low")

    results: list[LiquiditySweep] = []
    previous_time: datetime | None = None

    for index, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            raise ValueError(f"candle {index} must be a mapping")
        high = _number(candle.get("high"), f"candles[{index}].high")
        low = _number(candle.get("low"), f"candles[{index}].low")
        close = _number(candle.get("close"), f"candles[{index}].close")
        raw_time = candle.get("timestamp", candle.get("time"))
        if raw_time is None or not str(raw_time).strip():
            raise ValueError(f"candles[{index}].timestamp is required")
        time_text = str(raw_time)
        try:
            parsed_time = datetime.fromisoformat(time_text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"candles[{index}].timestamp must be ISO-8601") from exc
        if previous_time is not None and parsed_time < previous_time:
            raise ValueError("candles must be ordered chronologically")
        previous_time = parsed_time

        open_value = _number(candle.get("open"), f"candles[{index}].open")
        if high < max(open_value, low, close) or low > min(open_value, high, close):
            raise ValueError(f"candles[{index}] has inconsistent OHLC values")

        if high > pdh and close < pdh:
            results.append(LiquiditySweep(
                side="BEARISH",
                level_name="PDH",
                level=pdh,
                candle_time=time_text,
                candle_high=high,
                candle_low=low,
                candle_close=close,
                confirmation="Wick traded above PDH and candle closed back below it",
            ))
        if low < pdl and close > pdl:
            results.append(LiquiditySweep(
                side="BULLISH",
                level_name="PDL",
                level=pdl,
                candle_time=time_text,
                candle_high=high,
                candle_low=low,
                candle_close=close,
                confirmation="Wick traded below PDL and candle closed back above it",
            ))

    return results
