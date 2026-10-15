"""EMA crossover quant strategy with fail-closed output.

Consumes timestamped OHLCV DataFrames. Emits a candidate only; downstream live
validation / 10-minute confirmation must decide whether it becomes actionable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
import math

import numpy as np
import pandas as pd


@dataclass
class QuantSignal:
    decision: str = "WAIT"
    candidate_decision: Optional[str] = None
    strike: Optional[float] = None
    option_side: Optional[str] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    risk_reward: Optional[str] = None
    confidence: float = 0.0
    regime: str = "RANGE_BOUND"
    reasons: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)
    live_validation: dict[str, Any] = field(default_factory=lambda: {
        "verdict": "FAIL", "decision": "WAIT", "blocks": [],
    })
    engine_source: str = "EMA"
    atr_value: Optional[float] = None
    fast_ema: Optional[float] = None
    slow_ema: Optional[float] = None


def _empty_wait(reason: str) -> QuantSignal:
    return QuantSignal(
        reasons=[reason], guards=["NO_VALID_SETUP"],
        live_validation={"verdict": "FAIL", "decision": "WAIT", "blocks": [reason]},
    )


class EMAQuantEngine:
    def __init__(
        self, fast_period: int = 9, slow_period: int = 21,
        atr_period: int = 14, atr_sl_mult: float = 1.5,
        risk_reward: float = 2.0, max_risk_atr_mult: float = 2.0,
        use_rsi_filter: bool = True, rsi_period: int = 14,
        rsi_long: float = 50.0, rsi_short: float = 50.0,
        skip_first_minutes: int = 15, use_volume_filter: bool = True,
        volume_mult: float = 1.3,
    ):
        if min(fast_period, slow_period, atr_period, rsi_period) < 2:
            raise ValueError("Indicator periods must be >= 2")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        if min(atr_sl_mult, risk_reward, max_risk_atr_mult, volume_mult) <= 0:
            raise ValueError("Risk multipliers and volume_mult must be positive")
        if skip_first_minutes < 0:
            raise ValueError("skip_first_minutes cannot be negative")
        self.fast, self.slow = fast_period, slow_period
        self.atr_period, self.atr_sl_mult = atr_period, atr_sl_mult
        self.rr, self.max_risk_atr_mult = risk_reward, max_risk_atr_mult
        self.use_rsi, self.rsi_period = use_rsi_filter, rsi_period
        self.rsi_long, self.rsi_short = rsi_long, rsi_short
        self.skip_first_minutes = skip_first_minutes
        self.use_volume, self.volume_mult = use_volume_filter, volume_mult

    @staticmethod
    def _ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        # Wilder smoothing (alpha = 1 / period), not EMA span.
        return tr.ewm(alpha=1 / period, adjust=False).mean()

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _atm_strike(spot: float, step: int) -> float:
        # Half-up rounding avoids Python's banker's rounding.
        return float(math.floor(spot / step + 0.5) * step)

    def generate(
        self, df: pd.DataFrame, current_spot: float,
        strike_step: int = 50, current_time: Optional[datetime] = None,
    ) -> QuantSignal:
        if df is None or df.empty:
            return _empty_wait("Empty dataframe")
        if not isinstance(strike_step, int) or isinstance(strike_step, bool) or strike_step <= 0:
            return _empty_wait("Invalid strike_step")
        try:
            spot = float(current_spot)
        except (TypeError, ValueError):
            return _empty_wait("Invalid current_spot")
        if not math.isfinite(spot) or spot <= 0:
            return _empty_wait("Invalid current_spot")

        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return _empty_wait("Missing OHLC columns: " + ", ".join(sorted(required - set(df.columns))))

        work = df.copy()
        if not isinstance(work.index, pd.DatetimeIndex):
            return _empty_wait("DatetimeIndex required to identify completed candles/session")
        work = work.sort_index()
        if work.index.has_duplicates:
            return _empty_wait("Duplicate candle timestamps")
        if len(work) > 1:
            # Caller must pass newest candle last; treat it as forming and drop it.
            work = work.iloc[:-1]

        if self.skip_first_minutes > 0 and len(work):
            session_date = work.index[-1].date()
            same_day = work[work.index.date == session_date]
            if len(same_day):
                session_start = same_day.index[0]
                cutoff = session_start + pd.Timedelta(minutes=self.skip_first_minutes)
                work = work[work.index >= cutoff]

        numeric_cols = ["open", "high", "low", "close"]
        if "volume" in work.columns:
            numeric_cols.append("volume")
        for col in numeric_cols:
            work[col] = pd.to_numeric(work[col], errors="coerce")
        if work[numeric_cols].isna().any().any() or not np.isfinite(work[numeric_cols].to_numpy(dtype=float)).all():
            return _empty_wait("Non-finite OHLCV data")
        if (work[["open", "high", "low", "close"]] <= 0).any().any():
            return _empty_wait("Non-positive OHLC prices")
        invalid = (
            (work["high"] < work[["open", "low", "close"]].max(axis=1))
            | (work["low"] > work[["open", "high", "close"]].min(axis=1))
        )
        if invalid.any():
            return _empty_wait("Inconsistent OHLC candle")

        min_bars = max(self.slow, self.atr_period, self.rsi_period if self.use_rsi else 1) + 5
        if len(work) < min_bars:
            return _empty_wait(f"Insufficient completed candles ({len(work)} < {min_bars})")

        close, high, low = work["close"], work["high"], work["low"]
        fast, slow = self._ema(close, self.fast), self._ema(close, self.slow)
        atr = self._atr(high, low, close, self.atr_period)
        rsi = self._rsi(close, self.rsi_period) if self.use_rsi else None
        vals = [fast.iloc[-1], slow.iloc[-1], fast.iloc[-2], slow.iloc[-2],
                close.iloc[-1], high.iloc[-1], low.iloc[-1], atr.iloc[-1]]
        if not np.isfinite(np.asarray(vals, dtype=float)).all():
            return _empty_wait("Non-finite indicator value")
        curr_fast, curr_slow, prev_fast, prev_slow = map(float, vals[:4])
        entry = round(float(close.iloc[-1]), 2)
        curr_high, curr_low, curr_atr = map(float, vals[5:8])
        curr_rsi = float(rsi.iloc[-1]) if self.use_rsi else 50.0
        if not math.isfinite(curr_atr) or curr_atr <= 0:
            return _empty_wait("Invalid ATR")

        vol_ok = True
        if self.use_volume:
            if "volume" not in work.columns:
                return _empty_wait("Volume filter enabled but volume data is missing")
            if len(work) < 22:
                return _empty_wait("Insufficient candles for volume filter")
            avg_vol = float(work["volume"].iloc[-21:-1].mean())
            last_vol = float(work["volume"].iloc[-1])
            vol_ok = math.isfinite(avg_vol) and last_vol > avg_vol * self.volume_mult

        atm = self._atm_strike(spot, strike_step)
        bullish = prev_fast <= prev_slow and curr_fast > curr_slow
        bearish = prev_fast >= prev_slow and curr_fast < curr_slow
        if bullish and entry > curr_fast and entry > curr_slow and (not self.use_rsi or curr_rsi > self.rsi_long) and vol_ok:
            sl = round(min(curr_low, entry - self.atr_sl_mult * curr_atr), 2)
            risk = entry - sl
            if risk <= 0:
                return _empty_wait("Invalid risk (SL >= Entry)")
            risk = min(risk, self.max_risk_atr_mult * curr_atr)
            sl = round(entry - risk, 2)
            return QuantSignal(
                decision="CALL BUY", candidate_decision="CALL BUY", strike=atm, option_side="CE",
                entry=entry, stop_loss=sl, target=round(entry + risk * self.rr, 2),
                risk_reward=f"1 : {self.rr}", confidence=72.0 + (8 if curr_rsi > 55 else 0),
                regime="TRENDING_BULL",
                reasons=[f"EMA{self.fast} crossed above EMA{self.slow}", "Close above both EMAs",
                         f"ATR({self.atr_period})={curr_atr:.2f} (Wilder)", "Stop risk capped by ATR",
                         f"Target = {self.rr}R", f"Volume OK={vol_ok}"],
                live_validation={"verdict": "PASS", "decision": "CALL BUY", "blocks": []},
                atr_value=round(curr_atr, 2), fast_ema=round(curr_fast, 2), slow_ema=round(curr_slow, 2),
            )
        if bearish and entry < curr_fast and entry < curr_slow and (not self.use_rsi or curr_rsi < self.rsi_short) and vol_ok:
            sl = round(max(curr_high, entry + self.atr_sl_mult * curr_atr), 2)
            risk = sl - entry
            if risk <= 0:
                return _empty_wait("Invalid risk (SL <= Entry)")
            risk = min(risk, self.max_risk_atr_mult * curr_atr)
            sl = round(entry + risk, 2)
            return QuantSignal(
                decision="PUT BUY", candidate_decision="PUT BUY", strike=atm, option_side="PE",
                entry=entry, stop_loss=sl, target=round(entry - risk * self.rr, 2),
                risk_reward=f"1 : {self.rr}", confidence=72.0 + (8 if curr_rsi < 45 else 0),
                regime="TRENDING_BEAR",
                reasons=[f"EMA{self.fast} crossed below EMA{self.slow}", "Close below both EMAs",
                         f"ATR({self.atr_period})={curr_atr:.2f} (Wilder)", "Stop risk capped by ATR",
                         f"Target = {self.rr}R", f"Volume OK={vol_ok}"],
                live_validation={"verdict": "PASS", "decision": "PUT BUY", "blocks": []},
                atr_value=round(curr_atr, 2), fast_ema=round(curr_fast, 2), slow_ema=round(curr_slow, 2),
            )
        reasons = ["No valid EMA crossover + confirmation"]
        if not vol_ok:
            reasons.append("Volume filter failed")
        return _empty_wait(" | ".join(reasons))


def to_signal_data(q: QuantSignal, index: str = "", timestamp: str = "") -> dict[str, Any]:
    """Map EMA output to the app signal shape; candidates remain WAIT until gated."""
    payload = {
        "index": index, "decision": "WAIT", "candidate_decision": None,
        "strike": None, "option_side": None, "entry": None, "stop_loss": None,
        "target": None, "risk_reward": None, "confidence": 0.0, "regime": q.regime,
        "reasons": q.reasons, "guards": q.guards, "live_validation": q.live_validation,
        "engine_source": "EMA", "timestamp": timestamp,
    }
    if q.decision == "WAIT" or any(v is None for v in (q.entry, q.stop_loss, q.target)):
        return payload
    payload.update({
        "candidate_decision": q.decision, "strike": q.strike, "option_side": q.option_side,
        "entry": q.entry, "stop_loss": q.stop_loss, "target": q.target,
        "risk_reward": q.risk_reward, "confidence": q.confidence, "guards": [],
        "atr_value": q.atr_value, "fast_ema": q.fast_ema, "slow_ema": q.slow_ema,
    })
    return payload
