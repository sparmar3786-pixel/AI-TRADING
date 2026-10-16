"""Opening Range Breakout (ORB) research engine.

The engine emits a deterministic *candidate* only. It does not connect to a broker,
does not verify live data by itself, and must be passed through backend freshness,
risk, option-contract and server-owned 600-second stability gates before action.
Input is timestamped intraday OHLCV in chronological order; latest row is treated
as a still-forming candle and excluded by default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
import math
from typing import Any, Optional

import numpy as np
import pandas as pd

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class ORBSignal:
    decision: str = "WAIT"
    candidate_decision: Optional[str] = None
    option_side: Optional[str] = None
    strike: Optional[float] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    risk_reward: Optional[str] = None
    confidence: float = 0.0
    engine_source: str = "ORB"
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    atr_value: Optional[float] = None
    reasons: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)
    live_validation: dict[str, Any] = field(default_factory=lambda: {
        "verdict": "FAIL", "decision": "WAIT", "blocks": ["Backend validation required"],
    })


def _wait(reason: str, *guards: str) -> ORBSignal:
    return ORBSignal(
        reasons=[reason], guards=[*guards, "NO_VALID_SETUP"],
        live_validation={"verdict": "FAIL", "decision": "WAIT", "blocks": [reason]},
    )


class OpeningRangeBreakoutEngine:
    def __init__(
        self, opening_minutes: int = 15, atr_period: int = 14,
        risk_reward: float = 2.0, atr_buffer: float = 0.1,
        max_risk_atr_mult: float = 2.0, volume_mult: float = 1.2,
        use_volume_filter: bool = True, drop_forming_candle: bool = True,
        valid_until: str = "14:30",
    ):
        if opening_minutes not in (5, 10, 15, 30):
            raise ValueError("opening_minutes must be one of 5, 10, 15, 30")
        if atr_period < 2 or risk_reward <= 0 or atr_buffer < 0 or max_risk_atr_mult <= 0 or volume_mult <= 0:
            raise ValueError("Invalid ATR/risk/volume configuration")
        self.opening_minutes = opening_minutes
        self.atr_period = atr_period
        self.rr = float(risk_reward)
        self.atr_buffer = float(atr_buffer)
        self.max_risk_atr_mult = float(max_risk_atr_mult)
        self.volume_mult = float(volume_mult)
        self.use_volume_filter = bool(use_volume_filter)
        self.drop_forming = bool(drop_forming_candle)
        self.valid_until = datetime.strptime(valid_until, "%H:%M").time()

    @staticmethod
    def _now_ist(value: Optional[datetime]) -> datetime:
        value = value or datetime.now(IST)
        return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)

    @staticmethod
    def _atm(spot: float, step: int) -> float:
        return float(math.floor(spot / step + 0.5) * step)

    def generate(self, candles: pd.DataFrame, current_spot: float,
                 current_time: Optional[datetime] = None, strike_step: int = 50) -> ORBSignal:
        try:
            now = self._now_ist(current_time)
            spot = float(current_spot)
            if not math.isfinite(spot) or spot <= 0:
                return _wait("Invalid current spot", "INVALID_SPOT")
            if isinstance(strike_step, bool) or not isinstance(strike_step, int) or strike_step <= 0:
                return _wait("Invalid strike step", "INVALID_STRIKE_STEP")
            if now.weekday() >= 5 or now.time() < time(9, 15) or now.time() > self.valid_until:
                return _wait("Outside ORB trading window")
            if not isinstance(candles, pd.DataFrame) or candles.empty:
                return _wait("Intraday candles missing", "MISSING_CANDLES")
            df = candles.copy()
            if not isinstance(df.index, pd.DatetimeIndex):
                if "timestamp" not in df.columns:
                    return _wait("DatetimeIndex or timestamp column required", "INVALID_TIMESTAMPS")
                df.index = pd.to_datetime(df.pop("timestamp"), errors="coerce")
            if df.index.isna().any() or df.index.has_duplicates:
                return _wait("Invalid or duplicate candle timestamps", "INVALID_TIMESTAMPS")
            df.index = df.index.tz_localize(IST) if df.index.tz is None else df.index.tz_convert(IST)
            df = df.sort_index()
            df = df.loc[[ts.date() == now.date() and ts <= pd.Timestamp(now) for ts in df.index]]
            if self.drop_forming and not df.empty:
                df = df.iloc[:-1]
            if df.empty:
                return _wait("No completed candles after filtering", "NO_COMPLETED_CANDLES")
            candle_age = (now - df.index[-1].to_pydatetime()).total_seconds()
            if candle_age < 0 or candle_age > 360:
                return _wait("Latest completed candle is stale or future-dated", "STALE_CANDLES")
            required = {"open", "high", "low", "close"}
            if not required.issubset(df.columns):
                return _wait("Missing OHLC columns", "MISSING_OHLC")
            cols = ["open", "high", "low", "close"] + (["volume"] if "volume" in df.columns else [])
            for col in cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            if df[cols].isna().any().any() or not np.isfinite(df[cols].to_numpy(float)).all():
                return _wait("Non-finite candle data", "INVALID_CANDLES")
            if (df[["open", "high", "low", "close"]] <= 0).any().any():
                return _wait("Non-positive OHLC prices", "INVALID_CANDLES")
            if ((df.high < df[["open", "low", "close"]].max(axis=1)) |
                (df.low > df[["open", "high", "close"]].min(axis=1))).any():
                return _wait("Inconsistent OHLC candle", "INVALID_CANDLES")
            session_start = pd.Timestamp(datetime.combine(now.date(), time(9, 15), tzinfo=IST))
            range_end = session_start + pd.Timedelta(minutes=self.opening_minutes)
            opening = df.loc[(df.index >= session_start) & (df.index < range_end)]
            after = df.loc[df.index >= range_end]
            expected = max(1, self.opening_minutes // 5)
            if len(opening) < expected:
                return _wait("Opening range candles are incomplete", "OPENING_RANGE_INCOMPLETE")
            if after.empty:
                return _wait("No completed candle after opening range", "NO_BREAKOUT_CANDLE")
            if self.use_volume_filter:
                if "volume" not in df.columns:
                    return _wait("Volume filter enabled but volume is missing", "MISSING_VOLUME")
                if (df.volume < 0).any():
                    return _wait("Invalid volume values", "INVALID_VOLUME")
            or_high, or_low = float(opening.high.max()), float(opening.low.min())
            if not (math.isfinite(or_high) and math.isfinite(or_low) and or_high > or_low > 0):
                return _wait("Invalid opening range", "INVALID_OPENING_RANGE")
            last = after.iloc[-1]
            if self.use_volume_filter:
                prior = df.loc[df.index < after.index[-1], "volume"]
                if len(prior) < 3 or float(prior.tail(20).mean()) <= 0:
                    return _wait("Insufficient prior volume for breakout confirmation", "VOLUME_BASELINE_MISSING")
                if float(last.volume) <= float(prior.tail(20).mean()) * self.volume_mult:
                    return _wait("Breakout volume confirmation failed", "VOLUME_CONFIRMATION_FAILED")
            high, low, close = df.high.astype(float), df.low.astype(float), df.close.astype(float)
            tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
            atr = float(tr.ewm(alpha=1/self.atr_period, adjust=False).mean().iloc[-1])
            if not math.isfinite(atr) or atr <= 0:
                return _wait("ATR unavailable or invalid", "INVALID_ATR")
            entry = float(last.close)
            is_bull = entry > or_high and float(after.close.iloc[-2] if len(after) > 1 else last.open) <= or_high
            is_bear = entry < or_low and float(after.close.iloc[-2] if len(after) > 1 else last.open) >= or_low
            if not (is_bull ^ is_bear):
                return _wait("No confirmed opening-range breakout", "NO_BREAKOUT")
            side = "CALL BUY" if is_bull else "PUT BUY"
            sl = min(or_high, entry - self.atr_buffer * atr) if is_bull else max(or_low, entry + self.atr_buffer * atr)
            risk = entry - sl if is_bull else sl - entry
            risk = min(risk, self.max_risk_atr_mult * atr)
            if not math.isfinite(risk) or risk <= 0:
                return _wait("Invalid stop-loss distance", "INVALID_RISK")
            sl = round(entry-risk if is_bull else entry+risk, 2)
            target = round(entry + self.rr*risk if is_bull else entry-self.rr*risk, 2)
            return ORBSignal(
                decision=side, candidate_decision=side, option_side="CE" if is_bull else "PE",
                strike=self._atm(spot, strike_step), entry=round(entry, 2), stop_loss=sl, target=target,
                risk_reward=f"1 : {self.rr}", confidence=70.0,
                opening_range_high=round(or_high, 2), opening_range_low=round(or_low, 2),
                atr_value=round(atr, 2),
                reasons=[f"{self.opening_minutes}-minute opening range confirmed",
                         "Completed candle closed outside opening range",
                         "Breakout volume confirmed" if self.use_volume_filter else "Volume filter disabled",
                         "Underlying spot levels; downstream option-premium mapping required"],
                guards=["BACKEND_VALIDATION_REQUIRED"],
                live_validation={"verdict": "PENDING", "decision": "WAIT", "blocks": ["Freshness, option mapping, risk and 600-second gate required"]},
            )
        except (TypeError, ValueError, OverflowError) as exc:
            return _wait(f"Invalid input: {exc}", "INVALID_INPUT")
