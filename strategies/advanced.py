"""Original, dependency-free strategy indicators for research and paper trading.

Signals are hypotheses, not recommendations. Warm-up rows return None/WAIT;
no function places orders or claims a probability of profit.
"""
from __future__ import annotations
from math import isfinite, sqrt


def _numbers(values):
    out = []
    for value in values:
        try:
            n = float(value)
        except (TypeError, ValueError):
            raise ValueError("inputs must be numeric") from None
        if not isfinite(n):
            raise ValueError("inputs must be finite")
        out.append(n)
    return out


def bollinger_bands(closes, period=20, deviations=2.0):
    xs = _numbers(closes)
    if period < 2 or deviations <= 0:
        raise ValueError("period must be >= 2 and deviations > 0")
    lower, middle, upper = [None] * len(xs), [None] * len(xs), [None] * len(xs)
    for i in range(period - 1, len(xs)):
        window = xs[i - period + 1:i + 1]
        mean = sum(window) / period
        sd = sqrt(sum((x - mean) ** 2 for x in window) / period)
        middle[i], lower[i], upper[i] = mean, mean - deviations * sd, mean + deviations * sd
    return {"lower": lower, "middle": middle, "upper": upper}


def macd(closes, fast=12, slow=26, signal=9):
    if min(fast, slow, signal) < 1 or fast >= slow:
        raise ValueError("require 1 <= fast < slow and signal >= 1")
    from strategies.technical import ema
    xs = _numbers(closes)
    ef, es = ema(xs, fast), ema(xs, slow)
    line = [None if a is None or b is None else a - b for a, b in zip(ef, es)]
    valid = [x for x in line if x is not None]
    sig_valid = ema(valid, signal)
    sig, hist, j = [None] * len(xs), [None] * len(xs), 0
    for i, value in enumerate(line):
        if value is not None:
            sv = sig_valid[j]
            sig[i] = sv
            hist[i] = None if sv is None else value - sv
            j += 1
    return {"line": line, "signal": sig, "histogram": hist}


def donchian_channels(highs, lows, period=20):
    hi, lo = _numbers(highs), _numbers(lows)
    if len(hi) != len(lo):
        raise ValueError("highs and lows must have equal lengths")
    if period < 1:
        raise ValueError("period must be >= 1")
    if any(h < l for h, l in zip(hi, lo)):
        raise ValueError("high cannot be below low")
    upper, lower = [None] * len(hi), [None] * len(lo)
    # Channel at bar i only uses completed bars before i; avoids look-ahead.
    for i in range(period, len(hi)):
        upper[i] = max(hi[i - period:i])
        lower[i] = min(lo[i - period:i])
    return {"upper": upper, "lower": lower}


def vwap(highs, lows, closes, volumes):
    hi, lo, cl, vol = map(_numbers, (highs, lows, closes, volumes))
    if len({len(hi), len(lo), len(cl), len(vol)}) != 1:
        raise ValueError("OHLCV arrays must have equal lengths")
    if any(h < l for h, l in zip(hi, lo)) or any(v < 0 for v in vol):
        raise ValueError("invalid high/low or negative volume")
    pv = total = 0.0
    out = []
    for h, l, c, v in zip(hi, lo, cl, vol):
        pv += ((h + l + c) / 3.0) * v
        total += v
        out.append(pv / total if total > 0 else None)
    return out


def donchian_breakout(closes, highs, lows, period=20):
    xs = _numbers(closes)
    channels = donchian_channels(highs, lows, period)
    if len(xs) != len(channels["upper"]):
        raise ValueError("close/high/low arrays must have equal lengths")
    signals = []
    for close, upper, lower in zip(xs, channels["upper"], channels["lower"]):
        if upper is None or lower is None:
            signals.append("WAIT")
        elif close > upper:
            signals.append("LONG")
        elif close < lower:
            signals.append("SHORT")
        else:
            signals.append("WAIT")
    return signals


def bollinger_reentry(closes, period=20, deviations=2.0):
    xs = _numbers(closes)
    bands = bollinger_bands(xs, period, deviations)
    out, prior = [], "MID"
    for i, close in enumerate(xs):
        low, high = bands["lower"][i], bands["upper"][i]
        if low is None:
            out.append("WAIT")
            continue
        zone = "LOW" if close < low else "HIGH" if close > high else "MID"
        out.append("LONG" if prior == "LOW" and zone == "MID" else
                   "SHORT" if prior == "HIGH" and zone == "MID" else "WAIT")
        prior = zone
    return out
