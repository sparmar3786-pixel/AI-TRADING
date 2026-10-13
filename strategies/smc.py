"""Deterministic, candle-based SMC/ICT analysis for Indian index and MCX instruments.

This module is deliberately advisory: it emits NO TRADE unless the supplied
multi-timeframe candles provide a valid bias, POI, structure confirmation and
liquidity context. It never submits orders and never fabricates candles.
"""
from __future__ import annotations
from typing import Any, Iterable

OHLC = ("open", "high", "low", "close")


def _valid(candles: Iterable[dict[str, Any]]) -> list[dict[str, float]]:
    out = []
    for raw in candles:
        try:
            c = {k: float(raw[k]) for k in OHLC}
        except (KeyError, TypeError, ValueError):
            continue
        if c["high"] < max(c["open"], c["close"], c["low"]) or c["low"] > min(c["open"], c["close"], c["high"]):
            continue
        out.append(c)
    return out


def find_swings(candles: list[dict[str, float]], strength: int = 2) -> list[dict[str, float | int | str]]:
    """Return confirmed local pivot highs/lows; pivots require bars on both sides."""
    cs = _valid(candles)
    strength = max(1, int(strength))
    result = []
    for i in range(strength, len(cs) - strength):
        left, mid, right = cs[i-strength:i], cs[i], cs[i+1:i+strength+1]
        if all(mid["high"] > x["high"] for x in left + right):
            result.append({"index": i, "type": "high", "price": mid["high"]})
        if all(mid["low"] < x["low"] for x in left + right):
            result.append({"index": i, "type": "low", "price": mid["low"]})
    return result


def detect_fvg(candles: list[dict[str, float]]) -> list[dict[str, Any]]:
    cs = _valid(candles)
    zones = []
    for i in range(2, len(cs)):
        a, c = cs[i-2], cs[i]
        if a["high"] < c["low"]:
            zones.append({"type": "bullish", "top": c["low"], "bottom": a["high"], "index": i})
        if a["low"] > c["high"]:
            zones.append({"type": "bearish", "top": a["low"], "bottom": c["high"], "index": i})
    return zones


def detect_order_blocks(candles: list[dict[str, float]]) -> list[dict[str, Any]]:
    cs = _valid(candles)
    zones = []
    for i in range(1, len(cs)):
        prev, cur = cs[i-1], cs[i]
        if prev["close"] < prev["open"] and cur["close"] > prev["high"]:
            zones.append({"type": "bullish", "top": prev["high"], "bottom": prev["low"], "index": i-1})
        if prev["close"] > prev["open"] and cur["close"] < prev["low"]:
            zones.append({"type": "bearish", "top": prev["high"], "bottom": prev["low"], "index": i-1})
    return zones


def _structure(candles: list[dict[str, float]]) -> dict[str, Any]:
    cs = _valid(candles)
    swings = find_swings(cs)
    highs = [float(s["price"]) for s in swings if s["type"] == "high"]
    lows = [float(s["price"]) for s in swings if s["type"] == "low"]
    if len(cs) < 3 or not highs or not lows:
        return {"bias": "NO CLEAR BIAS", "bos": False, "choch": False, "swings": swings}
    last = cs[-1]
    bos_up = last["close"] > highs[-1]
    bos_down = last["close"] < lows[-1]
    # Conservative local shift: close breaks the latest opposing confirmed pivot.
    previous_bias = "BULLISH" if len(highs) >= 2 and len(lows) >= 2 and highs[-1] > highs[-2] and lows[-1] > lows[-2] else (
        "BEARISH" if len(highs) >= 2 and len(lows) >= 2 and highs[-1] < highs[-2] and lows[-1] < lows[-2] else "NO CLEAR BIAS")
    bias = "BULLISH" if bos_up else "BEARISH" if bos_down else previous_bias
    choch = (previous_bias == "BEARISH" and bos_up) or (previous_bias == "BULLISH" and bos_down)
    return {"bias": bias, "bos": bos_up or bos_down, "choch": choch, "swings": swings,
            "swing_high": highs[-1], "swing_low": lows[-1]}


def analyze_smc(
    htf_candles: list[dict[str, Any]],
    mtf_candles: list[dict[str, Any]],
    ltf_candles: list[dict[str, Any]],
    *,
    instrument: str = "NIFTY",
    liquidity_tolerance: float | None = None,
    in_killzone: bool = True,
) -> dict[str, Any]:
    """Analyze HTF bias + MTF structure + LTF POI/liquidity; no trade by default."""
    htf, mtf, ltf = _valid(htf_candles), _valid(mtf_candles), _valid(ltf_candles)
    name = str(instrument).upper()
    if liquidity_tolerance is None:
        # Price-unit tolerances, configurable by callers for the instrument/tick size.
        liquidity_tolerance = max((htf[-1]["close"] if htf else 1.0) * 0.00015, 0.05)
    bias_info, structure = _structure(htf), _structure(mtf)
    bias = bias_info["bias"]
    fvgs, obs = detect_fvg(ltf), detect_order_blocks(ltf)
    wanted = "bullish" if bias == "BULLISH" else "bearish"
    poi_candidates = [z for z in obs + fvgs if z["type"] == wanted]
    poi = max(poi_candidates, key=lambda z: z["index"]) if poi_candidates else None
    swings = find_swings(ltf)
    bsl, ssl = [], []
    for i, a in enumerate(swings):
        for b in swings[i+1:]:
            if a["type"] == b["type"] == "high" and abs(float(a["price"])-float(b["price"])) <= liquidity_tolerance:
                bsl.append(max(float(a["price"]), float(b["price"])))
            if a["type"] == b["type"] == "low" and abs(float(a["price"])-float(b["price"])) <= liquidity_tolerance:
                ssl.append(min(float(a["price"]), float(b["price"])))
    ltf_last = ltf[-1]["close"] if ltf else None
    choch = bool(structure.get("choch"))
    # BOS alone may confirm continuation; require structure break plus a directional POI.
    structure_ok = bool(structure.get("bos") or choch)
    liquidity_ok = bool(ssl if bias == "BULLISH" else bsl if bias == "BEARISH" else False)
    reasons = []
    if bias == "NO CLEAR BIAS": reasons.append("HTF bias is unclear")
    if not poi: reasons.append("No directional order block or FVG")
    if not structure_ok: reasons.append("No confirmed MTF BOS/CHoCH")
    if not liquidity_ok: reasons.append("No matching equal-low/high liquidity pool")
    if not in_killzone: reasons.append("Outside configured session window")
    if len(ltf) < 5 or len(mtf) < 5 or len(htf) < 5: reasons.append("Insufficient candles on one or more timeframes")
    trade_ok = not reasons
    signal = "LONG" if trade_ok and bias == "BULLISH" else "SHORT" if trade_ok and bias == "BEARISH" else "NO TRADE"
    entry = float(poi["top"] if bias == "BULLISH" else poi["bottom"]) if trade_ok and poi else None
    stop = float(poi["bottom"] if bias == "BULLISH" else poi["top"]) if trade_ok and poi else None
    return {
        "instrument": name, "signal": signal, "bias": bias, "entry": entry, "stop_loss": stop,
        "target_reference": "Next BSL" if signal == "LONG" else "Next SSL" if signal == "SHORT" else None,
        "htf": {"candles": len(htf), **bias_info}, "mtf": {"candles": len(mtf), **structure},
        "ltf": {"candles": len(ltf), "last_close": ltf_last, "order_blocks": obs, "fvgs": fvgs,
                "bsl": sorted(set(bsl)), "ssl": sorted(set(ssl)), "poi": poi},
        "in_killzone": bool(in_killzone), "liquidity_tolerance": float(liquidity_tolerance),
        "reasons": reasons, "execution_allowed": False,
        "note": "SMC/ICT is an advisory setup detector, not a profit guarantee or order authorization."
    }
