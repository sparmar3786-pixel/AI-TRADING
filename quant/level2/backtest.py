"""Small event-driven OHLC backtester with conservative intrabar fill rules."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Callable, Optional, Any
import math
import pandas as pd

@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 100000.0
    risk_fraction: float = 0.01
    slippage_bps: float = 5.0
    fee_per_unit_per_side: float = 0.0
    max_bars: int = 100000

@dataclass
class BacktestResult:
    metrics: dict[str, float]
    trades: list[dict[str, Any]]
    equity_curve: list[float]

def run_backtest(candles: pd.DataFrame, signal_fn: Callable[[pd.DataFrame, int], Optional[dict[str, Any]]], config: BacktestConfig = BacktestConfig()) -> BacktestResult:
    required = {"open", "high", "low", "close"}
    if not required.issubset(candles.columns): raise ValueError("candles require open/high/low/close")
    if candles.empty or len(candles) > config.max_bars: raise ValueError("empty data or bar limit exceeded")
    if config.initial_capital <= 0 or not 0 < config.risk_fraction <= 0.05 or config.slippage_bps < 0: raise ValueError("invalid backtest risk/cost configuration")
    df = candles.copy().reset_index(drop=True)
    for c in required: df[c] = pd.to_numeric(df[c], errors="coerce")
    if df[list(required)].isna().any().any() or (df[list(required)] <= 0).any().any(): raise ValueError("invalid OHLC values")
    if (df.high < df[["open", "low", "close"]].max(axis=1)).any() or (df.low > df[["open", "high", "close"]].min(axis=1)).any(): raise ValueError("inconsistent OHLC values")
    capital = config.initial_capital; equity = [capital]; trades = []; pos = None
    slip = config.slippage_bps / 10000.0
    for i in range(1, len(df)):
        row = df.iloc[i]
        # Signal function sees only bars strictly before the current bar. Fill at current open.
        if pos is not None:
            side = pos["side"]; stop_hit = row.low <= pos["stop"] if side == 1 else row.high >= pos["stop"]
            target_hit = row.high >= pos["target"] if side == 1 else row.low <= pos["target"]
            # If stop and target are both touched in one OHLC bar, pessimistically assume stop first.
            if stop_hit or target_hit:
                reason = "STOP" if stop_hit else "TARGET"
                raw = pos["stop"] if stop_hit else pos["target"]
                exit_price = raw * (1 - slip if side == 1 else 1 + slip)
                gross = side * (exit_price - pos["entry"]) * pos["qty"]
                fees = config.fee_per_unit_per_side * pos["qty"] * 2
                pnl = gross - fees; capital += pnl
                trades.append({"entry_index": pos["entry_index"], "exit_index": i, "side": side, "entry": pos["entry"], "exit": exit_price, "qty": pos["qty"], "pnl": pnl, "reason": reason})
                pos = None
        if pos is None:
            signal = signal_fn(df.iloc[:i].copy(), i)
            if signal and signal.get("side") in (1, -1):
                entry_raw = float(row.open); entry = entry_raw * (1 + slip if signal["side"] == 1 else 1 - slip)
                stop, target = float(signal.get("stop", 0)), float(signal.get("target", 0)); side = int(signal["side"])
                valid = stop > 0 and target > 0 and ((stop < entry < target) if side == 1 else (target < entry < stop))
                if valid:
                    risk_per_unit = abs(entry - stop); qty = math.floor((capital * config.risk_fraction) / risk_per_unit)
                    if qty > 0: pos = {"side": side, "entry": entry, "stop": stop, "target": target, "qty": qty, "entry_index": i}
        unrealized = 0.0 if pos is None else pos["side"] * (float(row.close) - pos["entry"]) * pos["qty"]
        equity.append(capital + unrealized)
    if pos is not None:
        row = df.iloc[-1]; exit_price = float(row.close) * (1 - slip if pos["side"] == 1 else 1 + slip)
        pnl = pos["side"] * (exit_price - pos["entry"]) * pos["qty"] - config.fee_per_unit_per_side * pos["qty"] * 2
        capital += pnl; trades.append({"entry_index": pos["entry_index"], "exit_index": len(df)-1, "side": pos["side"], "entry": pos["entry"], "exit": exit_price, "qty": pos["qty"], "pnl": pnl, "reason": "END_OF_DATA"})
        equity[-1] = capital
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]; losses = [t["pnl"] for t in trades if t["pnl"] < 0]
    peak = config.initial_capital; max_dd = 0.0
    for value in equity: peak = max(peak, value); max_dd = max(max_dd, (peak-value)/peak if peak else 0)
    metrics = {"initial_capital": config.initial_capital, "final_capital": capital, "net_return_pct": (capital/config.initial_capital-1)*100, "max_drawdown_pct": max_dd*100, "trade_count": float(len(trades)), "win_rate_pct": (len(wins)/len(trades)*100 if trades else 0.0), "profit_factor": (sum(wins)/abs(sum(losses)) if losses else (float("inf") if wins else 0.0)), "average_trade_pnl": (sum(t["pnl"] for t in trades)/len(trades) if trades else 0.0)}
    return BacktestResult(metrics, trades, equity)
