"""Small dependency-free close-to-close backtester for research only.

A signal observed at bar t is held for the return from t to t+1. Costs are
charged on position changes. It is not an execution simulator and omits spread,
market impact, taxes, funding, margin, gaps and instrument-specific contract rules.
"""
from __future__ import annotations
from math import isfinite, sqrt


def run_backtest(closes, signals, fee_rate=0.0005, slippage_rate=0.0005, periods_per_year=None):
    prices = []
    for value in closes:
        try:
            price = float(value)
        except (TypeError, ValueError):
            raise ValueError("closes must be numeric") from None
        if not isfinite(price) or price <= 0:
            raise ValueError("close prices must be finite and > 0")
        prices.append(price)
    if len(prices) != len(signals):
        raise ValueError("closes and signals must have equal lengths")
    if not isfinite(float(fee_rate)) or fee_rate < 0 or not isfinite(float(slippage_rate)) or slippage_rate < 0:
        raise ValueError("fee and slippage rates must be finite and non-negative")
    if periods_per_year is not None and periods_per_year <= 0:
        raise ValueError("periods_per_year must be > 0")
    mapping = {"LONG": 1.0, "SHORT": -1.0, "FLAT": 0.0, "WAIT": 0.0}
    positions = []
    for signal in signals:
        key = str(signal).strip().upper()
        if key not in mapping:
            raise ValueError("signals must be LONG, SHORT, FLAT, or WAIT")
        positions.append(mapping[key])
    returns, equity_curve = [], [1.0]
    prev_position = 0.0
    for i in range(1, len(prices)):
        held = positions[i - 1]
        turnover = abs(held - prev_position)
        gross = held * (prices[i] / prices[i - 1] - 1.0)
        net = gross - turnover * (float(fee_rate) + float(slippage_rate))
        returns.append(net)
        equity_curve.append(equity_curve[-1] * (1.0 + net))
        prev_position = held
    peak, max_dd = equity_curve[0], 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    avg = sum(returns) / len(returns) if returns else 0.0
    variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1) if len(returns) > 1 else 0.0
    std = sqrt(variance)
    sharpe = (avg / std * sqrt(periods_per_year)) if std > 0 and periods_per_year else (avg / std if std > 0 else None)
    changes = sum(1 for i in range(1, len(positions)) if positions[i] != positions[i - 1])
    return {"bars": len(prices), "return_observations": len(returns),
            "total_return": equity_curve[-1] - 1.0, "max_drawdown": max_dd,
            "sharpe": sharpe, "position_changes": changes, "equity_curve": equity_curve,
            "bar_returns": returns,
            "assumptions": ["signal delayed one bar", "close-to-close returns", "fee and slippage estimates only", "not a live execution simulator"]}
