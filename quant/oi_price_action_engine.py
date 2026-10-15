"""OI buildup + price-action confluence engine.

This is a candidate generator, not an execution engine. It intentionally returns
WAIT in the public decision field; a downstream freshness/risk/stability gate must
promote candidate_decision before any order can be considered.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Optional
import math

import numpy as np
import pandas as pd

IST = timezone(timedelta(hours=5, minutes=30))


class OIBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


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
    regime: str = "OI_PA"
    reasons: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)
    live_validation: dict[str, Any] = field(
        default_factory=lambda: {"verdict": "FAIL", "decision": "WAIT", "blocks": []}
    )
    engine_source: str = "OI_PA"
    pcr: Optional[float] = None
    total_ce_oi: Optional[float] = None
    total_pe_oi: Optional[float] = None
    ce_oi_change: Optional[float] = None
    pe_oi_change: Optional[float] = None
    oi_bias: Optional[str] = None
    price_oi_structure: Optional[str] = None
    pressure: Optional[str] = None
    support_strike: Optional[float] = None
    resistance_strike: Optional[float] = None
    atr_value: Optional[float] = None
    pa_tags: list[str] = field(default_factory=list)


def _wait(reason: str, **metadata: Any) -> QuantSignal:
    supplied_guards = metadata.pop("guards", [])
    guards = list(dict.fromkeys(["NO_VALID_SETUP", *supplied_guards]))
    return QuantSignal(
        reasons=[reason], guards=guards,
        live_validation={"verdict": "FAIL", "decision": "WAIT", "blocks": [reason]},
        **metadata,
    )


class OIPriceActionEngine:
    """Option-chain OI/PCR, breakout, candle pattern and ATR risk confluence."""

    def __init__(
        self, atr_period: int = 14, atr_sl_mult: float = 1.2,
        risk_reward: float = 1.8, min_oi_change_pct: float = 3.0,
        pcr_bull: float = 1.05, pcr_bear: float = 0.95,
        volume_mult: float = 1.3, min_score: int = 5,
        skip_first_minutes: int = 10, valid_from: str = "09:25",
        valid_until: str = "15:10", drop_forming_candle: bool = True,
        hold_bars: int = 1, wick_ratio: float = 2.0, use_depth_pressure: bool = True,
        max_candle_age_seconds: int = 360, max_option_chain_age_seconds: int = 90,
    ):
        if atr_period < 2 or atr_sl_mult <= 0 or risk_reward <= 0 or min_score < 1:
            raise ValueError("Invalid engine risk/scoring configuration")
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.rr = risk_reward
        self.min_oi_change_pct = min_oi_change_pct
        self.pcr_bull, self.pcr_bear = pcr_bull, pcr_bear
        self.volume_mult, self.min_score = volume_mult, min_score
        if hold_bars < 1 or wick_ratio <= 0:
            raise ValueError("Invalid price-action configuration")
        self.hold_bars, self.wick_ratio = hold_bars, wick_ratio
        if max_candle_age_seconds <= 0 or max_option_chain_age_seconds <= 0:
            raise ValueError("Freshness limits must be positive")
        self.max_candle_age_seconds = int(max_candle_age_seconds)
        self.max_option_chain_age_seconds = int(max_option_chain_age_seconds)
        self.use_depth_pressure = use_depth_pressure
        self.skip_first_minutes = skip_first_minutes
        self.valid_from = time.fromisoformat(valid_from)
        self.valid_until = time.fromisoformat(valid_until)
        self.drop_forming = drop_forming_candle

    @staticmethod
    def _number(value: Any) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _col(df: pd.DataFrame, *names: str) -> Optional[str]:
        lookup = {str(c).lower(): c for c in df.columns}
        return next((lookup[n] for n in names if n in lookup), None)

    def _chain(self, chain: pd.DataFrame) -> pd.DataFrame:
        df = chain.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        aliases = {
            "strike": ("strike", "strikeprice", "strike_price"),
            "ce_oi": ("ce_oi", "calloi", "call_oi", "ceoi"),
            "pe_oi": ("pe_oi", "putoi", "put_oi", "peoi"),
            "ce_oi_ch": ("ce_oi_change", "ce_changeinoi", "calloi_change", "ce_oi_ch"),
            "pe_oi_ch": ("pe_oi_change", "pe_changeinoi", "putoi_change", "pe_oi_ch"),
        }
        rename = {}
        for standard, candidates in aliases.items():
            found = self._col(df, *candidates)
            if found:
                rename[found] = standard
        df = df.rename(columns=rename)
        if "strike" not in df:
            raise ValueError("option_chain must contain strike")
        missing_oi = {"ce_oi", "pe_oi", "ce_oi_ch", "pe_oi_ch"} - set(df.columns)
        if missing_oi:
            raise ValueError("Option-chain fields missing: " + ", ".join(sorted(missing_oi)))
        for c in ("ce_oi", "pe_oi", "ce_oi_ch", "pe_oi_ch"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
        df = df.dropna(subset=["strike", "ce_oi", "pe_oi", "ce_oi_ch", "pe_oi_ch"])
        if df.empty or (df[["ce_oi", "pe_oi"]].values < 0).any():
            raise ValueError("option-chain OI values are invalid")
        return df

    def _pressure(self, df: pd.DataFrame, depth: Optional[dict[str, Any]] = None) -> str:
        pressure = "NONE"
        if len(df) >= 3 and {"open", "high", "low", "close"}.issubset(df.columns):
            last = df.iloc[-1]
            rng = max(float(last.high) - float(last.low), 1e-9)
            close_pos = (float(last.close) - float(last.low)) / rng
            vol_spike = False
            if "volume" in df.columns and len(df) >= 12:
                volumes = pd.to_numeric(df.volume, errors="coerce")
                avg = float(volumes.iloc[-12:-1].mean())
                latest = float(volumes.iloc[-1]) if self._number(volumes.iloc[-1]) else 0.0
                vol_spike = math.isfinite(avg) and avg > 0 and latest > avg * self.volume_mult
            if vol_spike and close_pos >= 0.7:
                pressure = "BUY_PRESSURE"
            elif vol_spike and close_pos <= 0.3:
                pressure = "SELL_PRESSURE"
        if self.use_depth_pressure and depth:
            try:
                bid = float(depth.get("total_buy_qty") or depth.get("bid_qty") or 0)
                ask = float(depth.get("total_sell_qty") or depth.get("ask_qty") or 0)
                if all(math.isfinite(x) and x >= 0 for x in (bid, ask)) and bid + ask > 0:
                    imbalance = (bid - ask) / (bid + ask)
                    if imbalance > 0.25:
                        pressure = "BUY_PRESSURE"
                    elif imbalance < -0.25:
                        pressure = "SELL_PRESSURE"
            except (TypeError, ValueError):
                pass
        return pressure

    def _rejection_wick(self, row: Any, side: str) -> bool:
        o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        body = max(abs(c - o), 1e-6)
        upper, lower = h - max(o, c), min(o, c) - l
        if side == "bull":
            return lower >= self.wick_ratio * body and upper <= body
        return upper >= self.wick_ratio * body and lower <= body

    def _two_candle_structure(self, df: pd.DataFrame) -> tuple[bool, bool, list[str]]:
        if len(df) < 2:
            return False, False, []
        a, b = df.iloc[-2], df.iloc[-1]
        bull = float(b.high) > float(a.high) and float(b.low) > float(a.low)
        bear = float(b.high) < float(a.high) and float(b.low) < float(a.low)
        tags = (["2-candle HH-HL structure"] if bull else []) + (["2-candle LH-LL structure"] if bear else [])
        return bull, bear, tags

    def generate(
        self, intraday_df: pd.DataFrame, option_chain: pd.DataFrame,
        current_spot: float, current_time: Optional[datetime] = None,
        strike_step: int = 50, fut_oi_now: Optional[float] = None,
        fut_oi_prev: Optional[float] = None, spot_ref: Optional[float] = None,
        market_depth: Optional[dict[str, Any]] = None,
        option_chain_timestamp: Optional[datetime] = None,
    ) -> QuantSignal:
        if not self._number(current_spot) or float(current_spot) <= 0:
            return _wait("Invalid spot price")
        now = current_time or datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)
        if not (self.valid_from <= now.time() <= self.valid_until):
            return _wait("Outside OI-PA trade window")
        if option_chain is None or option_chain.empty:
            return _wait("Option chain missing")
        if option_chain_timestamp is None:
            return _wait("Option-chain timestamp missing", guards=["QUOTE_TIMESTAMP_MISSING"])
        try:
            quote_time = option_chain_timestamp.replace(tzinfo=IST) if option_chain_timestamp.tzinfo is None else option_chain_timestamp.astimezone(IST)
        except (AttributeError, TypeError, ValueError):
            return _wait("Invalid option-chain timestamp", guards=["INVALID_QUOTE_TIMESTAMP"])
        quote_age = (now - quote_time).total_seconds()
        if quote_age < 0 or quote_age > self.max_option_chain_age_seconds:
            return _wait("Option chain is stale or future-dated", guards=["STALE_OPTION_CHAIN"])
        if strike_step <= 0:
            return _wait("Invalid strike step")
        required = {"open", "high", "low", "close"}
        if intraday_df is None or option_chain is None or option_chain.empty:
            return _wait("Option chain missing")
        if not required.issubset({str(c).lower() for c in intraday_df.columns}):
            return _wait("Required OHLC candles missing")
        df = intraday_df.copy()
        df.columns = [str(c).lower() for c in df.columns]
        if not isinstance(df.index, pd.DatetimeIndex):
            return _wait("Candles require a DatetimeIndex")
        df.index = df.index.tz_localize(IST) if df.index.tz is None else df.index.tz_convert(IST)
        df = df[(df.index.date == now.date()) & (df.index <= now)]
        if self.drop_forming and len(df) > 1:
            df = df.iloc[:-1]
        if df.empty:
            return _wait("No completed candles")
        candle_time = df.index[-1].to_pydatetime()
        candle_age = (now - candle_time).total_seconds()
        if candle_age < 0 or candle_age > self.max_candle_age_seconds:
            return _wait("Latest completed candle is stale or future-dated", guards=["STALE_CANDLES"])
        if len(df) < max(8, self.atr_period + 1):
            return _wait("Insufficient closed candles")
        if self.skip_first_minutes:
            df = df[df.index >= df.index[0] + pd.Timedelta(minutes=self.skip_first_minutes)]
        if len(df) < max(8, self.atr_period + 1):
            return _wait("Insufficient candles after time filters")
        for c in required:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=list(required))
        if len(df) < max(8, self.atr_period + 1):
            return _wait("Invalid candle values")
        if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any() or (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
            return _wait("Inconsistent OHLC candle")
        tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(),
                        (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.ewm(alpha=1 / self.atr_period, adjust=False).mean().iloc[-1])
        if not math.isfinite(atr) or atr <= 0:
            return _wait("Invalid ATR")
        try:
            chain = self._chain(option_chain)
        except ValueError as exc:
            return _wait(str(exc))
        atm = float(math.floor(float(current_spot) / strike_step + 0.5) * strike_step)
        band = chain[(chain.strike >= atm - 10 * strike_step) & (chain.strike <= atm + 10 * strike_step)]
        if band.empty:
            return _wait("No option-chain strikes around ATM")
        ce, pe = float(band.ce_oi.sum()), float(band.pe_oi.sum())
        cch, pch = float(band.ce_oi_ch.sum()), float(band.pe_oi_ch.sum())
        pcr = pe / ce if ce > 0 else None
        support = float(band.loc[band.pe_oi.idxmax(), "strike"])
        resistance = float(band.loc[band.ce_oi.idxmax(), "strike"])
        ce_base, pe_base = ce - cch, pe - pch
        ce_pct = cch / ce_base * 100 if ce_base > 0 else 0.0
        pe_pct = pch / pe_base * 100 if pe_base > 0 else 0.0
        bull = bear = 0
        reasons, tags = [], []
        if pch > 0 and abs(pe_pct) >= self.min_oi_change_pct: bull += 1
        if cch < 0 and abs(ce_pct) >= self.min_oi_change_pct: bull += 1
        if cch > 0 and abs(ce_pct) >= self.min_oi_change_pct: bear += 1
        if pch < 0 and abs(pe_pct) >= self.min_oi_change_pct: bear += 1
        if pcr is not None and pcr >= self.pcr_bull: bull += 1
        if pcr is not None and pcr <= self.pcr_bear: bear += 1
        bias = "BULLISH" if bull >= 2 and bull > bear else "BEARISH" if bear >= 2 and bear > bull else "NEUTRAL"
        prev, last = df.iloc[-2], df.iloc[-1]
        pressure = self._pressure(df, market_depth)
        prior_high = float(df.high.iloc[:-1].max())
        prior_low = float(df.low.iloc[:-1].min())
        if last.close > prior_high and bool(np.all(df.close.iloc[-self.hold_bars:] >= prior_high * 0.999)):
            bull += 2; reasons.append("PA: break & hold above prior high")
        if last.close < prior_low and bool(np.all(df.close.iloc[-self.hold_bars:] <= prior_low * 1.001)):
            bear += 2; reasons.append("PA: break & hold below prior low")
        bull_structure, bear_structure, structure_tags = self._two_candle_structure(df)
        if bull_structure: bull += 1
        if bear_structure: bear += 1
        tags.extend(structure_tags)
        if self._rejection_wick(last, "bull"):
            bull += 2; tags.append("Bullish rejection wick")
        if self._rejection_wick(last, "bear"):
            bear += 2; tags.append("Bearish rejection wick")
        if prev.close < prev.open and last.close > last.open and last.close >= prev.open and last.open <= prev.close:
            bull += 2; tags.append("Bullish engulfing")
        if prev.close > prev.open and last.close < last.open and last.close <= prev.open and last.open >= prev.close:
            bear += 2; tags.append("Bearish engulfing")
        if last.close > last.open and (last.close-last.low) / max(last.high-last.low, 1e-9) >= .75:
            bull += 1; tags.append("Strong close near high")
        if last.close < last.open and (last.close-last.low) / max(last.high-last.low, 1e-9) <= .25:
            bear += 1; tags.append("Strong close near low")
        if "volume" in df and len(df) >= 12:
            volume = pd.to_numeric(df["volume"], errors="coerce")
            avg = float(volume.iloc[-12:-1].mean())
            latest_volume = float(volume.iloc[-1]) if self._number(volume.iloc[-1]) else 0.0
            if self._number(avg) and avg > 0 and latest_volume > avg * self.volume_mult:
                if (last.close-last.low)/max(last.high-last.low, 1e-9) >= .7: bull += 1
                elif (last.close-last.low)/max(last.high-last.low, 1e-9) <= .3: bear += 1
        if pressure == "BUY_PRESSURE": bull += 1; reasons.append("Buy pressure (volume/depth)")
        elif pressure == "SELL_PRESSURE": bear += 1; reasons.append("Sell pressure (volume/depth)")
        if float(current_spot) <= support + strike_step and pch > 0 and abs(pe_pct) >= self.min_oi_change_pct:
            bull += 1; reasons.append(f"Near put-wall support {support}")
        if float(current_spot) >= resistance - strike_step and cch > 0 and abs(ce_pct) >= self.min_oi_change_pct:
            bear += 1; reasons.append(f"Near call-wall resistance {resistance}")
        if bias == "BULLISH": bull += 2
        elif bias == "BEARISH": bear += 2
        structure = "UNKNOWN"
        if fut_oi_now is not None and fut_oi_prev is not None and self._number(fut_oi_now) and self._number(fut_oi_prev) and fut_oi_prev > 0:
            up, oi_up = float(current_spot) > float(spot_ref if spot_ref is not None else df.close.iloc[0]), fut_oi_now > fut_oi_prev
            structure = "LONG_BUILDUP" if up and oi_up else "SHORT_COVERING" if up else "SHORT_BUILDUP" if oi_up else "LONG_UNWINDING"
            if structure in ("LONG_BUILDUP", "SHORT_COVERING"): bull += 1
            else: bear += 1
        if bull >= self.min_score and bull > bear: decision, side = "CALL BUY", "CE"
        elif bear >= self.min_score and bear > bull: decision, side = "PUT BUY", "PE"
        else: return _wait("Weak OI + price-action confluence", pcr=pcr, total_ce_oi=ce, total_pe_oi=pe, ce_oi_change=cch, pe_oi_change=pch, oi_bias=bias, price_oi_structure=structure, pressure=pressure, support_strike=support, resistance_strike=resistance, atr_value=round(atr, 2), pa_tags=tags, reasons=reasons + [f"Scores bull={bull} bear={bear}"])
        entry = float(current_spot)
        if decision == "CALL BUY":
            sl = min(float(last.low), entry - self.atr_sl_mult * atr)
            risk = entry - sl
            target = min(entry + risk * self.rr, resistance) if resistance > entry else entry + risk * self.rr
        else:
            sl = max(float(last.high), entry + self.atr_sl_mult * atr)
            risk = sl - entry
            target = max(entry - risk * self.rr, support) if support < entry else entry - risk * self.rr
        if risk <= 0 or not all(map(math.isfinite, (sl, target))) or (decision == "CALL BUY" and target <= entry) or (decision == "PUT BUY" and target >= entry):
            return _wait("Invalid stop-loss/target geometry")
        return QuantSignal(
            decision="WAIT", candidate_decision=decision, strike=atm, option_side=side,
            entry=round(entry, 2), stop_loss=round(sl, 2), target=round(target, 2),
            risk_reward=f"1 : {self.rr}", confidence=min(90.0, 50.0 + max(bull, bear) * 6),
            regime=f"OI_PA_{bias}", reasons=reasons + tags + [f"Scores bull={bull} bear={bear}"],
            guards=["DOWNSTREAM_RISK_AND_STABILITY_GATE_REQUIRED"],
            live_validation={"verdict": "PENDING", "decision": "WAIT", "blocks": ["Await downstream freshness, risk and 10-minute stability validation"]},
            pcr=round(pcr, 3) if pcr is not None else None, total_ce_oi=ce, total_pe_oi=pe,
            ce_oi_change=cch, pe_oi_change=pch, oi_bias=bias, price_oi_structure=structure,
            pressure=pressure, support_strike=support, resistance_strike=resistance, atr_value=round(atr, 2),
            pa_tags=tags,
        )


def to_signal_data(q: QuantSignal, index: str = "", timestamp: str = "", data_fresh: bool = True) -> dict[str, Any]:
    """Serialize safely: candidate prices remain hidden until downstream promotion."""
    wait = q.candidate_decision is None or not data_fresh
    return {
        "index": index, "decision": "WAIT",
        "candidate_decision": None if wait else q.candidate_decision,
        "strike": None if wait else q.strike, "option_side": None if wait else q.option_side,
        "entry": None if wait else q.entry, "stop_loss": None if wait else q.stop_loss,
        "target": None if wait else q.target, "risk_reward": None if wait else q.risk_reward,
        "confidence": 0.0 if wait else q.confidence, "regime": q.regime,
        "reasons": q.reasons, "guards": q.guards, "live_validation": q.live_validation,
        "engine_source": "OI_PA", "entry_price_basis": "UNDERLYING_SPOT", "stop_loss_price_basis": "UNDERLYING_SPOT", "target_price_basis": "UNDERLYING_SPOT", "pcr": q.pcr, "total_ce_oi": q.total_ce_oi, "total_pe_oi": q.total_pe_oi,
        "ce_oi_change": q.ce_oi_change,
        "pe_oi_change": q.pe_oi_change, "oi_bias": q.oi_bias,
        "price_oi_structure": q.price_oi_structure, "pressure": q.pressure,
        "support_strike": q.support_strike, "resistance_strike": q.resistance_strike,
        "atr_value": q.atr_value, "pa_tags": q.pa_tags, "timestamp": timestamp,
        "data_fresh": data_fresh,
    }
