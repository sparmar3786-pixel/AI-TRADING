"""Isolated failed-reclaim continuation engine for PDH/PDL.

This module intentionally does not redefine or modify the shared EMA QuantSignal.
It exposes FailedMoveSignal and failed_move_to_signal_data to avoid symbol/function
collisions with other strategy modules. A candidate is never directly actionable:
the API mapper keeps decision=WAIT until downstream live validation/stability gates.
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
class FailedMoveSignal:
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
    engine_source: str = "FAILED_MOVE"
    pdh: Optional[float] = None
    pdl: Optional[float] = None
    breakout_level: Optional[float] = None
    hold_bars: Optional[int] = None
    atr_value: Optional[float] = None


def _wait(reason: str, *, guards: Optional[list[str]] = None) -> FailedMoveSignal:
    return FailedMoveSignal(
        decision="WAIT",
        reasons=[reason],
        guards=list(guards or []) + ["NO_VALID_SETUP"],
        live_validation={"verdict": "FAIL", "decision": "WAIT", "blocks": [reason]},
    )


def _finite_positive(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return number


class FailedMoveFadeEngine:
    """Detect acceptance outside yesterday's high/low (continuation, not reversal).

    CALL candidate: at least hold_bars completed closes above PDH.
    PUT candidate: at least hold_bars completed closes below PDL.
    The latest hold bars must agree on exactly one side. Input candles are expected
    to be chronological OHLCV with a DatetimeIndex. Missing/invalid data fails closed.
    """

    def __init__(
        self,
        hold_bars: int = 3,
        atr_period: int = 14,
        atr_sl_buffer_mult: float = 0.25,
        max_risk_atr_mult: float = 2.0,
        risk_reward: float = 2.0,
        min_rr: float = 1.0,
        use_volume_filter: bool = True,
        volume_mult: float = 1.3,
        skip_first_minutes: int = 15,
        valid_from: str = "09:30",
        valid_until: str = "14:00",
        drop_forming_candle: bool = True,
    ):
        if hold_bars < 1 or atr_period < 2:
            raise ValueError("hold_bars must be >= 1 and atr_period >= 2")
        if atr_sl_buffer_mult < 0 or max_risk_atr_mult <= 0:
            raise ValueError("ATR buffer must be >= 0 and max ATR risk must be > 0")
        if risk_reward <= 0 or min_rr <= 0 or risk_reward < min_rr:
            raise ValueError("risk_reward must be positive and >= min_rr")
        if volume_mult <= 0 or skip_first_minutes < 0:
            raise ValueError("volume_mult must be > 0 and skip_first_minutes >= 0")
        self.hold_bars = int(hold_bars)
        self.atr_period = int(atr_period)
        self.atr_sl_buffer_mult = float(atr_sl_buffer_mult)
        self.max_risk_atr_mult = float(max_risk_atr_mult)
        self.rr = float(risk_reward)
        self.min_rr = float(min_rr)
        self.use_volume = bool(use_volume_filter)
        self.volume_mult = float(volume_mult)
        self.skip_first_minutes = int(skip_first_minutes)
        self.valid_from = datetime.strptime(valid_from, "%H:%M").time()
        self.valid_until = datetime.strptime(valid_until, "%H:%M").time()
        if self.valid_from > self.valid_until:
            raise ValueError("valid_from must not be later than valid_until")
        self.drop_forming = bool(drop_forming_candle)

    @staticmethod
    def _to_ist(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=IST)
        return value.astimezone(IST)

    @staticmethod
    def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError("DataFrame is missing or empty")
        df = frame.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" not in df.columns:
                raise ValueError("DatetimeIndex or date column is required")
            df["date"] = pd.to_datetime(df["date"], errors="raise")
            df = df.set_index("date")
        if df.index.tz is None:
            df.index = df.index.tz_localize(IST)
        else:
            df.index = df.index.tz_convert(IST)
        if df.index.has_duplicates:
            raise ValueError("Duplicate candle timestamps are not allowed")
        return df.sort_index()

    @staticmethod
    def _validate_ohlc(df: pd.DataFrame) -> None:
        required = {"high", "low", "close"}
        missing = required.difference(df.columns)
        if missing:
            raise ValueError(f"Missing OHLC columns: {', '.join(sorted(missing))}")
        for col in required:
            values = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values <= 0).any():
                raise ValueError(f"{col} contains non-finite or non-positive values")
        if (df["high"] < df["low"]).any():
            raise ValueError("OHLC invalid: high below low")
        if (df["close"] > df["high"]).any() or (df["close"] < df["low"]).any():
            raise ValueError("OHLC invalid: close outside candle range")

    def _previous_levels(self, daily_df: pd.DataFrame, current_date: date) -> tuple[float, float]:
        daily = self._normalize_frame(daily_df)
        self._validate_ohlc(daily)
        prior = daily.loc[[ts.date() < current_date for ts in daily.index]]
        if prior.empty:
            raise ValueError("No previous-session daily candle for PDH/PDL")
        # Sorted index means the final prior row is the latest available prior session.
        row = prior.iloc[-1]
        pdh, pdl = float(row["high"]), float(row["low"])
        if not (math.isfinite(pdh) and math.isfinite(pdl) and pdh > pdl > 0):
            raise ValueError("Invalid previous-session PDH/PDL")
        return pdh, pdl

    def _atr(self, df: pd.DataFrame) -> float:
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        true_range = pd.concat(
            [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
            axis=1,
        ).max(axis=1)
        value = true_range.ewm(alpha=1 / self.atr_period, adjust=False).mean().iloc[-1]
        if not np.isfinite(value) or float(value) <= 0:
            raise ValueError("ATR is invalid")
        return float(value)

    @staticmethod
    def _atm(spot: float, step: int) -> float:
        return float(math.floor(spot / step + 0.5) * step)

    def generate(
        self,
        daily_df: pd.DataFrame,
        intraday_df: pd.DataFrame,
        current_spot: float,
        current_time: Optional[datetime] = None,
        strike_step: int = 50,
    ) -> FailedMoveSignal:
        try:
            spot = _finite_positive(current_spot, "current_spot")
            if isinstance(strike_step, bool) or int(strike_step) != strike_step or strike_step <= 0:
                raise ValueError("strike_step must be a positive integer")
            now = self._to_ist(current_time or datetime.now(IST))
            if not (self.valid_from <= now.time() <= self.valid_until):
                return _wait(f"Outside failed-move window {self.valid_from:%H:%M}-{self.valid_until:%H:%M}")

            pdh, pdl = self._previous_levels(daily_df, now.date())
            df = self._normalize_frame(intraday_df)
            self._validate_ohlc(df)
            if self.use_volume:
                if "volume" not in df.columns:
                    return _wait("Volume filter enabled but volume column is missing", guards=["MISSING_VOLUME"])
                vol = pd.to_numeric(df["volume"], errors="coerce").to_numpy(dtype=float)
                if not np.isfinite(vol).all() or (vol < 0).any():
                    return _wait("Invalid volume data", guards=["INVALID_VOLUME"])

            df = df.loc[[ts.date() == now.date() and ts <= pd.Timestamp(now) for ts in df.index]]
            if self.drop_forming and len(df) > 0:
                df = df.iloc[:-1]
            session_open = pd.Timestamp(datetime.combine(now.date(), time(9, 15), tzinfo=IST))
            eligible_after = session_open + pd.Timedelta(minutes=self.skip_first_minutes)
            df = df.loc[df.index >= eligible_after]
            if df.empty:
                return _wait("No completed intraday bars after filters", guards=["NO_COMPLETED_CANDLES"])
            candle_age = (now - df.index[-1].to_pydatetime()).total_seconds()
            if candle_age < 0 or candle_age > 360:
                return _wait("Latest completed candle is stale or future-dated", guards=["STALE_CANDLES"])
            if len(df) < max(self.hold_bars + 2, self.atr_period + 2):
                return _wait("Insufficient completed intraday bars after filters")

            atr = self._atr(df)
            closes = df["close"].astype(float).to_numpy()
            recent = closes[-self.hold_bars:]
            above = bool(np.all(recent > pdh))
            below = bool(np.all(recent < pdl)
            )
            if above == below:
                return _wait(f"No unique level acceptance: PDH_held={above}, PDL_held={below}")

            decision = "CALL BUY" if above else "PUT BUY"
            level = pdh if above else pdl
            # Require an actual close beyond the level somewhere in today's filtered data.
            if above and not bool((closes > pdh).any()):
                return _wait("No completed close above PDH")
            if below and not bool((closes < pdl).any()):
                return _wait("No completed close below PDL")

            if self.use_volume:
                if len(df) < 21:
                    return _wait("Insufficient bars for volume confirmation", guards=["VOLUME_WARMUP"])
                volumes = df["volume"].astype(float)
                baseline = float(volumes.iloc[-21:-1].mean())
                last_volume = float(volumes.iloc[-1])
                if not np.isfinite(baseline) or baseline <= 0 or last_volume < baseline * self.volume_mult:
                    return _wait("Volume confirmation failed", guards=["VOLUME_FILTER"])
                volume_ratio = last_volume / baseline
            else:
                volume_ratio = 1.0

            buffer = max(0.0, self.atr_sl_buffer_mult * atr)
            raw_sl = level - buffer if above else level + buffer
            raw_risk = spot - raw_sl if above else raw_sl - spot
            if not math.isfinite(raw_risk) or raw_risk <= 0:
                return _wait("Invalid risk: spot is not beyond buffered breakout level")
            max_risk = self.max_risk_atr_mult * atr
            risk = min(raw_risk, max_risk)
            stop_loss = spot - risk if above else spot + risk
            target = spot + risk * self.rr if above else spot - risk * self.rr
            if stop_loss <= 0 or target <= 0 or not all(map(math.isfinite, (stop_loss, target))):
                return _wait("Invalid stop-loss or target")

            strike = self._atm(spot, int(strike_step))
            conf = min(90.0, 68.0 + (7.0 if self.hold_bars >= 3 else 0.0) + (5.0 if volume_ratio >= 1.3 else 0.0))
            reasons = [
                f"{'PDH' if above else 'PDL'} acceptance: {self.hold_bars} completed closes outside level",
                f"Breakout level: {level:.2f}",
                f"ATR({self.atr_period}): {atr:.2f}; risk capped at {self.max_risk_atr_mult:.2f}×ATR",
                f"Volume ratio: {volume_ratio:.2f}×" if self.use_volume else "Volume filter disabled",
                f"Target: {self.rr:.2f}R",
            ]
            return FailedMoveSignal(
                decision=decision,
                candidate_decision=decision,
                strike=strike,
                option_side="CE" if above else "PE",
                entry=round(spot, 2),
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                risk_reward=f"1 : {self.rr:g}",
                confidence=conf,
                regime="FAILED_RECLAIM_CONT_BULL" if above else "FAILED_RECLAIM_CONT_BEAR",
                reasons=reasons,
                guards=["RISK_CAPPED"] if raw_risk > max_risk else [],
                live_validation={"verdict": "PENDING", "decision": "WAIT", "blocks": ["Downstream freshness, risk, option-premium mapping and 10-minute stability validation required"]},
                engine_source="FAILED_MOVE",
                pdh=round(pdh, 2),
                pdl=round(pdl, 2),
                breakout_level=round(level, 2),
                hold_bars=self.hold_bars,
                atr_value=round(atr, 2),
            )
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            return _wait(str(exc), guards=["INVALID_OR_INCOMPLETE_DATA"])


def failed_move_to_signal_data(
    signal: FailedMoveSignal,
    *,
    index: str,
    timestamp: str,
    data_fresh: bool,
) -> dict[str, Any]:
    """API mapping; stale data or a candidate is never emitted as an actionable BUY."""
    common = {
        "index": index,
        "timestamp": timestamp,
        "data_fresh": bool(data_fresh),
        "engine_source": signal.engine_source,
        "pdh": signal.pdh,
        "pdl": signal.pdl,
        "breakout_level": signal.breakout_level,
        "hold_bars": signal.hold_bars,
        "atr_value": signal.atr_value,
        "entry_price_basis": "UNDERLYING_SPOT",
        "stop_loss_price_basis": "UNDERLYING_SPOT",
        "target_price_basis": "UNDERLYING_SPOT",
    }
    if not data_fresh:
        return {
            **common,
            "decision": "WAIT",
            "candidate_decision": None,
            "strike": None,
            "option_side": None,
            "entry": None,
            "stop_loss": None,
            "target": None,
            "risk_reward": None,
            "confidence": 0.0,
            "regime": "RANGE_BOUND",
            "reasons": ["Stale market data — candidate blocked"],
            "guards": ["STALE_DATA"],
            "live_validation": {"verdict": "FAIL", "decision": "WAIT", "blocks": ["STALE_DATA"]},
            "signal_stability": {"state": "NOT_ACTIONABLE", "required_minutes": 10},
        }

    valid_candidate = (
        signal.decision in {"CALL BUY", "PUT BUY"}
        and signal.entry is not None
        and signal.stop_loss is not None
        and signal.target is not None
        and signal.strike is not None
        and signal.option_side in {"CE", "PE"}
    )
    if not valid_candidate:
        return {
            **common,
            "decision": "WAIT",
            "candidate_decision": None,
            "strike": None,
            "option_side": None,
            "entry": None,
            "stop_loss": None,
            "target": None,
            "risk_reward": None,
            "confidence": 0.0,
            "regime": signal.regime,
            "reasons": signal.reasons or ["No valid setup"],
            "guards": signal.guards or ["NO_VALID_SETUP"],
            "live_validation": {"verdict": "FAIL", "decision": "WAIT", "blocks": signal.reasons or ["No valid setup"]},
            "signal_stability": {"state": "NOT_ACTIONABLE", "required_minutes": 10},
        }

    return {
        **common,
        "decision": "WAIT",
        "candidate_decision": signal.decision,
        "strike": signal.strike,
        "option_side": signal.option_side,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "target": signal.target,
        "risk_reward": signal.risk_reward,
        "confidence": signal.confidence,
        "regime": signal.regime,
        "reasons": list(signal.reasons),
        "guards": list(signal.guards),
        "live_validation": {"verdict": "PENDING", "decision": "WAIT", "blocks": ["Downstream risk and stability validation required"]},
        "signal_stability": {"state": "CONFIRMING", "required_minutes": 10, "elapsed_seconds": 0, "remaining_seconds": 600},
    }


__all__ = ["FailedMoveFadeEngine", "FailedMoveSignal", "failed_move_to_signal_data"]
