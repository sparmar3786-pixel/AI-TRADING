"""Original broker-neutral technical indicators for research and paper trading."""
from math import isfinite


def _values(values):
    out = []
    for value in values:
        try:
            n = float(value)
        except (TypeError, ValueError):
            raise ValueError("Inputs must be numeric") from None
        if not isfinite(n):
            raise ValueError("Inputs must be finite")
        out.append(n)
    return out


def sma(values, period):
    xs = _values(values)
    if period < 1:
        raise ValueError("period must be >= 1")
    out, running = [None] * len(xs), 0.0
    for i, x in enumerate(xs):
        running += x
        if i >= period:
            running -= xs[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values, period):
    xs = _values(values)
    if period < 1:
        raise ValueError("period must be >= 1")
    out = [None] * len(xs)
    if len(xs) < period:
        return out
    previous = sum(xs[:period]) / period
    out[period - 1] = previous
    alpha = 2.0 / (period + 1)
    for i in range(period, len(xs)):
        previous = alpha * xs[i] + (1.0 - alpha) * previous
        out[i] = previous
    return out


def rsi(closes, period=14):
    xs = _values(closes)
    if period < 1:
        raise ValueError("period must be >= 1")
    out = [None] * len(xs)
    if len(xs) <= period:
        return out
    gains = [max(xs[i] - xs[i-1], 0.0) for i in range(1, len(xs))]
    losses = [max(xs[i-1] - xs[i], 0.0) for i in range(1, len(xs))]
    ag, al = sum(gains[:period]) / period, sum(losses[:period]) / period

    def calc(g, loss):
        if loss == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + g / loss)

    out[period] = calc(ag, al)
    for i in range(period + 1, len(xs)):
        ag = (ag * (period - 1) + gains[i-1]) / period
        al = (al * (period - 1) + losses[i-1]) / period
        out[i] = calc(ag, al)
    return out


def atr(highs, lows, closes, period=14):
    hi, lo, cl = _values(highs), _values(lows), _values(closes)
    if not (len(hi) == len(lo) == len(cl)):
        raise ValueError("highs, lows, closes must have equal lengths")
    if period < 1:
        raise ValueError("period must be >= 1")
    tr = []
    for i, (h, low) in enumerate(zip(hi, lo)):
        if h < low:
            raise ValueError("high cannot be below low")
        tr.append(h-low if i == 0 else max(h-low, abs(h-cl[i-1]), abs(low-cl[i-1])))
    out = [None] * len(tr)
    if len(tr) < period:
        return out
    prev = sum(tr[:period]) / period
    out[period-1] = prev
    for i in range(period, len(tr)):
        prev = (prev * (period-1) + tr[i]) / period
        out[i] = prev
    return out


def ema_crossover(closes, fast=9, slow=21):
    if fast >= slow:
        raise ValueError("fast period must be less than slow period")
    ef, es = ema(closes, fast), ema(closes, slow)
    out, previous = [], None
    for f, s in zip(ef, es):
        if f is None or s is None:
            out.append("WAIT")
            continue
        state = "LONG" if f > s else "SHORT" if f < s else "WAIT"
        out.append(state if state != previous else "WAIT")
        previous = state
    return out


def rsi_reversion(closes, period=14, oversold=30, overbought=70):
    if not (0 <= oversold < overbought <= 100):
        raise ValueError("invalid RSI thresholds")
    out, previous_zone = [], "NONE"
    for value in rsi(closes, period):
        if value is None:
            out.append("WAIT")
            continue
        zone = "LOW" if value <= oversold else "HIGH" if value >= overbought else "MID"
        out.append("LONG" if previous_zone == "LOW" and zone == "MID" else
                   "SHORT" if previous_zone == "HIGH" and zone == "MID" else "WAIT")
        previous_zone = zone
    return out
