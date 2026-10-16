"""Intraday VWAP reclaim/rejection candidate engine (research only).

Requires timestamped OHLCV. VWAP is reset each IST session; incomplete/missing
volume, stale/future candles, or insufficient history return WAIT. Candidates use
underlying prices, not option premiums, and require downstream live/risk/stability
validation before they can become actionable.
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
class VWAPSignal:
    decision: str = "WAIT"
    candidate_decision: Optional[str] = None
    option_side: Optional[str] = None
    strike: Optional[float] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    risk_reward: Optional[str] = None
    confidence: float = 0.0
    engine_source: str = "VWAP"
    vwap: Optional[float] = None
    atr_value: Optional[float] = None
    reasons: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)
    live_validation: dict[str, Any] = field(default_factory=lambda: {
        "verdict": "FAIL", "decision": "WAIT", "blocks": ["Backend validation required"],
    })


def _wait(reason: str, *guards: str) -> VWAPSignal:
    return VWAPSignal(
        reasons=[reason], guards=[*guards, "NO_VALID_SETUP"],
        live_validation={"verdict": "FAIL", "decision": "WAIT", "blocks": [reason]},
    )


class VWAPStrategyEngine:
    def __init__(self, atr_period: int = 14, risk_reward: float = 2.0,
                 atr_sl_mult: float = 1.2, max_risk_atr_mult: float = 2.0,
                 volume_mult: float = 1.0, use_volume_filter: bool = True,
                 drop_forming_candle: bool = True, valid_from: str = "09:30",
                 valid_until: str = "14:45"):
        if atr_period < 2 or risk_reward <= 0 or atr_sl_mult <= 0 or max_risk_atr_mult <= 0 or volume_mult <= 0:
            raise ValueError("Invalid ATR/risk/volume configuration")
        self.atr_period, self.rr = int(atr_period), float(risk_reward)
        self.atr_sl_mult, self.max_risk_atr_mult = float(atr_sl_mult), float(max_risk_atr_mult)
        self.volume_mult, self.use_volume_filter = float(volume_mult), bool(use_volume_filter)
        self.drop_forming = bool(drop_forming_candle)
        self.valid_from = datetime.strptime(valid_from, "%H:%M").time()
        self.valid_until = datetime.strptime(valid_until, "%H:%M").time()
        if self.valid_from > self.valid_until:
            raise ValueError("valid_from must be <= valid_until")

    @staticmethod
    def _now_ist(value: Optional[datetime]) -> datetime:
        value = value or datetime.now(IST)
        return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)

    @staticmethod
    def _atm(spot: float, step: int) -> float:
        return float(math.floor(spot / step + 0.5) * step)

    def generate(self, candles: pd.DataFrame, current_spot: float,
                 current_time: Optional[datetime] = None, strike_step: int = 50) -> VWAPSignal:
        try:
            now = self._now_ist(current_time)
            spot = float(current_spot)
            if not math.isfinite(spot) or spot <= 0:
                return _wait("Invalid current spot", "INVALID_SPOT")
            if isinstance(strike_step, bool) or not isinstance(strike_step, int) or strike_step <= 0:
                return _wait("Invalid strike step", "INVALID_STRIKE_STEP")
            if now.weekday() >= 5 or not (self.valid_from <= now.time() <= self.valid_until):
                return _wait("Outside VWAP strategy window")
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
            required = {"open", "high", "low", "close", "volume"}
            if not required.issubset(df.columns):
                return _wait("VWAP requires OHLCV including volume", "MISSING_OHLCV")
            for col in required:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            if df[list(required)].isna().any().any() or not np.isfinite(df[list(required)].to_numpy(float)).all():
                return _wait("Non-finite OHLCV data", "INVALID_CANDLES")
            if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df.volume < 0).any():
                return _wait("Non-positive prices or negative volume", "INVALID_CANDLES")
            if ((df.high < df[["open", "low", "close"]].max(axis=1)) |
                (df.low > df[["open", "high", "close"]].min(axis=1))).any():
                return _wait("Inconsistent OHLC candle", "INVALID_CANDLES")
            session_start = pd.Timestamp(datetime.combine(now.date(), time(9, 15), tzinfo=IST))
            df = df.loc[df.index >= session_start]
            if len(df) < max(5, self.atr_period + 2):
                return _wait("Insufficient completed candles for VWAP/ATR", "INSUFFICIENT_HISTORY")
            if (df.volume <= 0).all():
                return _wait("No positive traded volume", "INVALID_VOLUME")
            typical = (df.high + df.low + df.close) / 3.0
            total_volume = df.volume.cumsum()
            vwap_series = (typical * df.volume).cumsum() / total_volume.replace(0, np.nan)
            if vwap_series.isna().any():
                return _wait("VWAP cannot be computed from volume", "INVALID_VWAP")
            close, high, low = df.close.astype(float), df.high.astype(float), df.low.astype(float)
            tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
            atr_series = tr.ewm(alpha=1/self.atr_period, adjust=False).mean()
            vwap_now, atr = float(vwap_series.iloc[-1]), float(atr_series.iloc[-1])
            if not math.isfinite(vwap_now) or not math.isfinite(atr) or atr <= 0:
                return _wait("VWAP or ATR invalid", "INVALID_INDICATOR")
            prev_close, prev_vwap = float(close.iloc[-2]), float(vwap_series.iloc[-2])
            entry = float(close.iloc[-1])
            bullish = prev_close <= prev_vwap and entry > vwap_now
            bearish = prev_close >= prev_vwap and entry < vwap_now
            if self.use_volume_filter:
                baseline = float(df.volume.iloc[-6:-1].mean())
                if not math.isfinite(baseline) or baseline <= 0 or float(df.volume.iloc[-1]) < baseline * self.volume_mult:
                    return _wait("VWAP cross lacks volume confirmation", "VOLUME_CONFIRMATION_FAILED")
            if not (bullish ^ bearish):
                return _wait("No confirmed VWAP cross on completed candles", "NO_VWAP_CROSS")
            is_bull = bullish
            risk = min(self.atr_sl_mult * atr, self.max_risk_atr_mult * atr)
            if not math.isfinite(risk) or risk <= 0:
                return _wait("Invalid ATR risk distance", "INVALID_RISK")
            sl = round(entry-risk if is_bull else entry+risk, 2)
            target = round(entry+self.rr*risk if is_bull else entry-self.rr*risk, 2)
            side = "CALL BUY" if is_bull else "PUT BUY"
            return VWAPSignal(
                decision=side, candidate_decision=side, option_side="CE" if is_bull else "PE",
                strike=self._atm(spot, strike_step), entry=round(entry, 2), stop_loss=sl,
                target=target, risk_reward=f"1 : {self.rr}", confidence=68.0,
                vwap=round(vwap_now, 2), atr_value=round(atr, 2),
                reasons=["Session VWAP reset at 09:15 IST", "Completed candle crossed VWAP",
                         "Volume confirmation passed" if self.use_volume_filter else "Volume filter disabled",
                         "Underlying spot levels; downstream option-premium mapping required"],
                guards=["BACKEND_VALIDATION_REQUIRED"],
                live_validation={"verdict": "PENDING", "decision": "WAIT", "blocks": ["Freshness, option mapping, risk and 600-second gate required"]},
            )
        except (TypeError, ValueError, OverflowError) as exc:
            return _wait(f"Invalid input: {exc}", "INVALID_INPUT")
