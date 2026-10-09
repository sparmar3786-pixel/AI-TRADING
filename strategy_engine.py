"""Original, broker-neutral strategy confluence helpers for AI-TRADING.

This module is a research filter, not an order router. It intentionally treats
missing evidence as UNKNOWN and never invents a signal or claims a win rate.
Feed it normalized, timestamp-validated Angel One data from the server backend.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _direction(a: float, b: float) -> str:
    if a > b:
        return "BULLISH"
    if a < b:
        return "BEARISH"
    return "MIXED"


def evaluate_confluence(
    candidate: str,
    *,
    ema_fast: Any = None,
    ema_slow: Any = None,
    macd_hist: Any = None,
    rsi14: Any = None,
    timeframe_closes: dict[str, list[Any]] | None = None,
    option_bid: Any = None,
    option_ask: Any = None,
    option_ltp: Any = None,
    call_oi_change: Any = None,
    put_oi_change: Any = None,
) -> dict[str, Any]:
    """Return explainable alignment diagnostics for CALL BUY / PUT BUY / WAIT.

    `alignment_score` is a bounded evidence-alignment score, not a probability
    of profit. This function does not validate timestamps, create trade levels,
    or place orders; those are separate mandatory backend gates.
    """
    action = str(candidate or "WAIT").strip().upper()
    wanted = {"CALL BUY": "BULLISH", "PUT BUY": "BEARISH"}.get(action, "UNKNOWN")
    checks: dict[str, str] = {}
    points = 0
    known = 0

    def add(name: str, state: str, weight: int = 1) -> None:
        nonlocal points, known
        checks[name] = state
        if state != "UNKNOWN":
            known += 1
            if state == wanted:
                points += weight
            elif state in ("BULLISH", "BEARISH") and wanted != "UNKNOWN":
                points -= weight

    fast, slow = _num(ema_fast), _num(ema_slow)
    add("ema_trend", "UNKNOWN" if fast is None or slow is None else _direction(fast, slow), 2)

    macd = _num(macd_hist)
    add("macd_momentum", "UNKNOWN" if macd is None else ("BULLISH" if macd > 0 else "BEARISH" if macd < 0 else "MIXED"), 2)

    rsi = _num(rsi14)
    rsi_state = "UNKNOWN" if rsi is None else ("BULLISH" if rsi >= 55 else "BEARISH" if rsi <= 45 else "MIXED")
    add("rsi_regime", rsi_state, 1)

    tf_states: dict[str, str] = {}
    for name, raw in (timeframe_closes or {}).items():
        values = [_num(v) for v in raw[-5:]]
        values = [v for v in values if v is not None and v > 0]
        if len(values) < 3:
            state = "UNKNOWN"
        elif values[-1] > values[-2] and values[-1] > values[0]:
            state = "BULLISH"
        elif values[-1] < values[-2] and values[-1] < values[0]:
            state = "BEARISH"
        else:
            state = "MIXED"
        tf_states[str(name)] = state
        if state in ("BULLISH", "BEARISH") and wanted != "UNKNOWN":
            known += 1
            points += 2 if state == wanted else -2
    directional = [s for s in tf_states.values() if s in ("BULLISH", "BEARISH")]
    checks["multi_timeframe"] = (
        "UNKNOWN" if not directional else
        "CONFLICT" if len(set(directional)) > 1 else
        "ALIGNED" if directional[0] == wanted else
        "OPPOSED" if wanted != "UNKNOWN" else directional[0]
    )

    bid, ask, ltp = _num(option_bid), _num(option_ask), _num(option_ltp)
    if bid is None or ask is None or ltp is None or not (0 < bid <= ltp <= ask):
        checks["option_spread"] = "UNKNOWN"
    else:
        spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
        checks["option_spread"] = "TIGHT" if spread_pct <= 2 else "MODERATE" if spread_pct <= 8 else "WIDE"
        known += 1
        points += 1 if spread_pct <= 2 else -1 if spread_pct > 8 else 0

    call_oi, put_oi = _num(call_oi_change), _num(put_oi_change)
    if call_oi is None or put_oi is None:
        checks["oi_change_context"] = "UNKNOWN"
    elif call_oi > put_oi:
        checks["oi_change_context"] = "CALL_OI_CHANGE_DOMINANT"
    elif put_oi > call_oi:
        checks["oi_change_context"] = "PUT_OI_CHANGE_DOMINANT"
    else:
        checks["oi_change_context"] = "BALANCED"

    score = round(max(0.0, min(100.0, 50.0 + points * 5.0)), 1) if known else None
    return {
        "candidate": action if action in ("CALL BUY", "PUT BUY") else "WAIT",
        "candidate_direction": wanted,
        "alignment_score": score,
        "score_semantics": "Evidence alignment only; not a probability of profit",
        "known_evidence_count": known,
        "checks": checks,
        "timeframes": tf_states,
    }
