"""Fail-closed expiry-day Hero Zero option candidate engine.

This module only emits a *candidate*. It never authorizes broker orders.
Live backend integration must supply verified contract expiry, fresh spot/candles,
and timestamped option quotes; the downstream risk/stability gate remains mandatory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Any, Optional

import numpy as np
import pandas as pd

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class HeroZeroSignal:
    decision: str = "WAIT"
    candidate_decision: Optional[str] = None
    strike: Optional[float] = None
    option_side: Optional[str] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    risk_reward: Optional[str] = None
    confidence: float = 0.0
    regime: str = "EXPIRY_HERO_ZERO"
    reasons: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)
    live_validation: dict[str, Any] = field(default_factory=lambda: {
        "verdict": "FAIL", "decision": "WAIT", "blocks": [],
    })
    engine_source: str = "HERO_ZERO"
    spot: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    premium_band: Optional[str] = None
    trigger: Optional[str] = None


def _wait(reason: str, guard: str = "NO_VALID_SETUP") -> HeroZeroSignal:
    return HeroZeroSignal(
        reasons=[reason], guards=[guard],
        live_validation={"verdict": "FAIL", "decision": "WAIT", "blocks": [reason]},
    )


def _positive(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be finite and positive") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return number


class HeroZeroEngine:
    """Late-session expiry-only breakout candidate engine; fail closed by default."""

    def __init__(
        self,
        min_premium: float = 5.0,
        max_premium: float = 25.0,
        strike_offset: int = 1,
        hold_bars: int = 2,
        valid_from: str = "13:30",
        valid_until: str = "14:45",
        target_mult: float = 3.0,
        soft_sl_pct: float = 0.50,
        use_soft_sl: bool = True,
        require_volume: bool = True,
        volume_mult: float = 1.2,
        max_candle_age_seconds: int = 600,
        max_quote_age_seconds: int = 15,
        max_spread_pct: float = 5.0,
        drop_forming_candle: bool = True,
    ):
        if not (math.isfinite(min_premium) and math.isfinite(max_premium)
                and 0 < min_premium <= max_premium):
            raise ValueError("premium band must satisfy 0 < min_premium <= max_premium")
        if isinstance(strike_offset, bool) or int(strike_offset) != strike_offset or strike_offset < 0:
            raise ValueError("strike_offset must be a non-negative integer")
        if isinstance(hold_bars, bool) or int(hold_bars) != hold_bars or hold_bars < 1:
            raise ValueError("hold_bars must be an integer >= 1")
        if not math.isfinite(target_mult) or target_mult <= 1:
            raise ValueError("target_mult must be finite and > 1")
        if not math.isfinite(soft_sl_pct) or not 0 < soft_sl_pct < 1:
            raise ValueError("soft_sl_pct must be between 0 and 1")
        if not math.isfinite(volume_mult) or volume_mult <= 0:
            raise ValueError("volume_mult must be finite and > 0")
        if max_candle_age_seconds <= 0 or max_quote_age_seconds <= 0:
            raise ValueError("freshness limits must be positive")
        if not math.isfinite(max_spread_pct) or max_spread_pct <= 0:
            raise ValueError("max_spread_pct must be finite and > 0")
        self.min_premium, self.max_premium = float(min_premium), float(max_premium)
        self.strike_offset, self.hold_bars = int(strike_offset), int(hold_bars)
        self.valid_from = datetime.strptime(valid_from, "%H:%M").time()
        self.valid_until = datetime.strptime(valid_until, "%H:%M").time()
        if self.valid_from > self.valid_until:
            raise ValueError("valid_from must not be later than valid_until")
        self.target_mult, self.soft_sl_pct = float(target_mult), float(soft_sl_pct)
        self.use_soft_sl, self.require_volume = bool(use_soft_sl), bool(require_volume)
        self.volume_mult = float(volume_mult)
        self.max_candle_age_seconds = int(max_candle_age_seconds)
        self.max_quote_age_seconds = int(max_quote_age_seconds)
        self.max_spread_pct = float(max_spread_pct)
        self.drop_forming_candle = bool(drop_forming_candle)

    @staticmethod
    def _now_ist(value: Optional[datetime]) -> datetime:
        dt = value or datetime.now(IST)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=IST)
        return dt.astimezone(IST)

    @staticmethod
    def _frame(frame: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError("candle data missing or empty")
        df = frame.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            if "timestamp" not in df.columns:
                raise ValueError("DatetimeIndex or timestamp column required")
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
            df = df.set_index("timestamp")
        if df.index.tz is None:
            df.index = df.index.tz_localize(IST)
        else:
            df.index = df.index.tz_convert(IST)
        if df.index.has_duplicates:
            raise ValueError("duplicate candle timestamps")
        return df.sort_index()

    @staticmethod
    def _validate_ohlcv(df: pd.DataFrame, require_volume: bool) -> None:
        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError("missing OHLC columns: " + ", ".join(sorted(missing)))
        for col in required:
            values = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values <= 0).any():
                raise ValueError(f"invalid {col} values")
        if (df["high"] < df["low"]).any() or (df["close"] > df["high"]).any() or (df["close"] < df["low"]).any():
            raise ValueError("inconsistent OHLC ranges")
        if (df["open"] > df["high"]).any() or (df["open"] < df["low"]).any():
            raise ValueError("open outside candle range")
        if require_volume:
            if "volume" not in df.columns:
                raise ValueError("required volume column missing")
            values = pd.to_numeric(df["volume"], errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError("invalid volume values")

    @staticmethod
    def _atm(spot: float, step: int) -> float:
        return float(math.floor(spot / step + 0.5) * step)

    def _premium(self, chain: Optional[pd.DataFrame], strike: float, side: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
        if not isinstance(chain, pd.DataFrame) or chain.empty or "strike" not in chain.columns:
            return None, None, None
        df = chain.copy()
        if {"ce_ltp", "pe_ltp"}.issubset(df.columns):
            rows = df[pd.to_numeric(df["strike"], errors="coerce") == strike]
            if len(rows) != 1:
                return None, None, None
            row = rows.iloc[0]
            ltp = row["ce_ltp"] if side == "CE" else row["pe_ltp"]
            bid = row.get("ce_bid" if side == "CE" else "pe_bid")
            ask = row.get("ce_ask" if side == "CE" else "pe_ask")
        elif {"option_type", "ltp"}.issubset(df.columns):
            mask = (pd.to_numeric(df["strike"], errors="coerce") == strike) & (df["option_type"].astype(str).str.upper() == side)
            rows = df[mask]
            if len(rows) != 1:
                return None, None, None
            row = rows.iloc[0]
            ltp, bid, ask = row["ltp"], row.get("bid"), row.get("ask")
        else:
            return None, None, None
        try:
            premium = _positive(ltp, "option premium")
            bid_value = _positive(bid, "bid") if bid is not None and pd.notna(bid) else None
            ask_value = _positive(ask, "ask") if ask is not None and pd.notna(ask) else None
            if (bid_value is None) != (ask_value is None):
                return None, None, None
            if bid_value is not None and ask_value < bid_value:
                return None, None, None
            return premium, bid_value, ask_value
        except ValueError:
            return None, None, None

    def generate(
        self,
        intraday_df: pd.DataFrame,
        current_spot: float,
        is_expiry_day: bool,
        option_chain: Optional[pd.DataFrame] = None,
        current_time: Optional[datetime] = None,
        strike_step: int = 50,
        expiry_date: Optional[date] = None,
        option_chain_timestamp: Optional[datetime] = None,
        day_high: Optional[float] = None,
        day_low: Optional[float] = None,
        pdh: Optional[float] = None,
        pdl: Optional[float] = None,
    ) -> HeroZeroSignal:
        try:
            now = self._now_ist(current_time)
            if is_expiry_day is not True or expiry_date is None or expiry_date != now.date():
                return _wait("Verified contract expiry date missing or does not match today", "EXPIRY_NOT_VERIFIED")
            if not (self.valid_from <= now.time() <= self.valid_until):
                return _wait(f"Outside Hero Zero window ({self.valid_from:%H:%M}-{self.valid_until:%H:%M})", "TIME_WINDOW")
            spot = _positive(current_spot, "current_spot")
            if isinstance(strike_step, bool) or int(strike_step) != strike_step or strike_step <= 0:
                return _wait("Invalid strike_step", "INVALID_STRIKE_STEP")
            if option_chain_timestamp is None:
                return _wait("Option-chain quote timestamp missing", "QUOTE_TIMESTAMP_MISSING")
            quote_time = self._now_ist(option_chain_timestamp)
            quote_age = (now - quote_time).total_seconds()
            if quote_age < 0 or quote_age > self.max_quote_age_seconds:
                return _wait("Option-chain quote is stale or future-dated", "STALE_OPTION_CHAIN")

            df = self._frame(intraday_df)
            self._validate_ohlcv(df, self.require_volume)
            df = df.loc[(df.index.date == now.date()) & (df.index <= pd.Timestamp(now))]
            if self.drop_forming_candle and not df.empty:
                df = df.iloc[:-1]
            if len(df) < max(5, self.hold_bars + 2):
                return _wait("Insufficient completed intraday bars", "INSUFFICIENT_BARS")
            age = (now - df.index[-1].to_pydatetime()).total_seconds()
            if age < 0 or age > self.max_candle_age_seconds:
                return _wait("Latest completed candle is stale or future-dated", "STALE_CANDLES")

            # The resistance/support reference excludes all bars used to confirm the hold.
            hold = df.iloc[-self.hold_bars:]
            history = df.iloc[:-self.hold_bars]
            if history.empty:
                return _wait("No pre-breakout reference candles", "INSUFFICIENT_HISTORY")
            prior_high = float(history["high"].max())
            prior_low = float(history["low"].min())
            closes = hold["close"].astype(float)
            bull = bool((closes > prior_high).all())
            bear = bool((closes < prior_low).all())

            pdh_value = _positive(pdh, "PDH") if pdh is not None else None
            pdl_value = _positive(pdl, "PDL") if pdl is not None else None
            pdh_cont = pdh_value is not None and bool((closes > pdh_value).all()) and bool((df["high"] > pdh_value).any())
            pdl_cont = pdl_value is not None and bool((closes < pdl_value).all()) and bool((df["low"] < pdl_value).any())
            bull = bull or pdh_cont
            bear = bear or pdl_cont
            if bull == bear:
                return _wait("No unique confirmed breakout/hold", "NO_CONFIRMED_BREAKOUT")

            if self.require_volume:
                if len(df) < 21:
                    return _wait("Insufficient completed bars for volume baseline", "VOLUME_WARMUP")
                volumes = pd.to_numeric(df["volume"], errors="coerce")
                baseline = float(volumes.iloc[-21:-1].mean())
                last_volume = float(volumes.iloc[-1])
                if not math.isfinite(baseline) or baseline <= 0 or last_volume <= baseline * self.volume_mult:
                    return _wait("Volume confirmation failed", "VOLUME_FILTER")

            decision = "CALL BUY" if bull else "PUT BUY"
            side = "CE" if bull else "PE"
            strike = self._atm(spot, int(strike_step)) + (self.strike_offset * int(strike_step) * (1 if bull else -1))
            premium, bid, ask = self._premium(option_chain, strike, side)
            if premium is None:
                return _wait(f"Missing or invalid premium for {strike} {side}", "INVALID_OPTION_QUOTE")
            if bid is not None and ask is not None:
                mid = (bid + ask) / 2.0
                if mid <= 0 or ((ask - bid) / mid * 100.0) > self.max_spread_pct:
                    return _wait("Option bid-ask spread exceeds configured limit", "WIDE_SPREAD")
            if not self.min_premium <= premium <= self.max_premium:
                return _wait(f"Premium {premium:.2f} outside band [{self.min_premium}, {self.max_premium}]", "PREMIUM_BAND")
            entry = round(premium, 2)
            sl = round(entry * (1 - self.soft_sl_pct), 2) if self.use_soft_sl else None
            target = round(entry * self.target_mult, 2)
            trigger = "PDH_CONTINUATION" if pdh_cont and bull else "PDL_CONTINUATION" if pdl_cont and bear else "PRIOR_RANGE_BREAK"
            return HeroZeroSignal(
                decision=decision, candidate_decision=decision, strike=strike, option_side=side,
                entry=entry, stop_loss=sl, target=target,
                risk_reward=f"1 : {self.target_mult:.1f} (premium)", confidence=0.0,
                reasons=[
                    f"Expiry Hero Zero candidate; trigger={trigger}",
                    f"Strike {strike} {side}; observed premium ₹{entry:.2f}",
                    f"Premium band ₹{self.min_premium:.2f}-₹{self.max_premium:.2f}",
                    "Candidate only; downstream risk, stability and execution checks required",
                    "Premium loss can be total; target and soft stop are not guaranteed fills",
                ],
                guards=["HERO_ZERO_FIXED_CAPITAL_REQUIRED", "DOWNSTREAM_RISK_GATE_REQUIRED"],
                live_validation={"verdict": "CANDIDATE_ONLY", "decision": "WAIT", "blocks": ["Downstream validation pending"]},
                spot=round(spot, 2),
                day_high=round(float(day_high), 2) if day_high is not None and math.isfinite(float(day_high)) else round(float(df["high"].max()), 2),
                day_low=round(float(day_low), 2) if day_low is not None and math.isfinite(float(day_low)) else round(float(df["low"].min()), 2),
                premium_band=f"{self.min_premium:g}-{self.max_premium:g}", trigger=trigger,
            )
        except (ValueError, TypeError, OverflowError, KeyError, IndexError) as exc:
            return _wait(f"Invalid or incomplete Hero Zero input: {exc}", "INVALID_INPUT")


def hero_zero_to_signal_data(
    signal: HeroZeroSignal, *, index: str = "", timestamp: str = "", data_fresh: bool = True,
) -> dict[str, Any]:
    """Serialize without bypassing the app's downstream WAIT/stability gate."""
    valid_candidate = data_fresh and signal.candidate_decision in {"CALL BUY", "PUT BUY"} and signal.entry is not None
    if not valid_candidate:
        reason = "Stale data invalidates Hero Zero candidate" if not data_fresh else (signal.reasons or ["No valid candidate"])[0]
        return {
            "index": index, "decision": "WAIT", "candidate_decision": None,
            "strike": None, "option_side": None, "entry": None, "stop_loss": None, "target": None,
            "risk_reward": None, "confidence": 0.0, "regime": "EXPIRY_HERO_ZERO",
            "reasons": [reason], "guards": list(dict.fromkeys(signal.guards + ["STALE_DATA" if not data_fresh else "NO_VALID_SETUP"])),
            "live_validation": {"verdict": "FAIL", "decision": "WAIT", "blocks": [reason]},
            "engine_source": "HERO_ZERO", "timestamp": timestamp, "data_fresh": data_fresh, "hero_zero": True,
        }
    return {
        "index": index, "decision": "WAIT", "candidate_decision": signal.candidate_decision,
        "strike": signal.strike, "option_side": signal.option_side, "entry": signal.entry,
        "stop_loss": signal.stop_loss, "target": signal.target, "risk_reward": signal.risk_reward,
        "confidence": 0.0, "regime": signal.regime, "reasons": signal.reasons,
        "guards": list(dict.fromkeys(signal.guards + ["HERO_ZERO_FIXED_CAPITAL", "DOWNSTREAM_RISK_GATE_REQUIRED"])),
        "live_validation": signal.live_validation, "engine_source": "HERO_ZERO",
        "spot": signal.spot, "day_high": signal.day_high, "day_low": signal.day_low,
        "premium_band": signal.premium_band, "trigger": signal.trigger,
        "timestamp": timestamp, "data_fresh": data_fresh, "hero_zero": True,
    }
