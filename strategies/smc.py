"""Deterministic, candle-based SMC/ICT analysis for Indian index and MCX instruments.

This module is deliberately advisory: it emits NO TRADE unless the supplied
multi-timeframe candles provide a valid bias, POI, structure confirmation and
liquidity context. It never submits orders and never fabricates candles.
"""
from __future__ import annotations
from datetime import datetime, time, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

OHLC = ("open", "high", "low", "close")


def ict_killzone_status(now_utc: datetime | None = None) -> dict[str, Any]:
    """Return the active standard ICT killzone using DST-aware New York time."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(ZoneInfo("America/New_York"))
    clock = local.time().replace(tzinfo=None)
    windows = (
        ("ASIA", time(20, 0), None),
        ("LONDON", time(2, 0), time(5, 0)),
        ("NEW_YORK_AM", time(7, 0), time(10, 0)),
        ("LONDON_CLOSE", time(10, 0), time(12, 0)),
    )
    active_window = None
    for name, start, end in windows:
        active = clock >= start if end is None else start <= clock < end
        if active:
            active_window = name
            break
    return {
        "active": active_window is not None,
        "window": active_window,
        "timezone": "America/New_York",
        "local_time": local.isoformat(),
    }


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


def analyze_guardeer(
    htf_candles: list[dict[str, Any]],
    mtf_candles: list[dict[str, Any]],
    ltf_candles: list[dict[str, Any]],
    *, instrument: str = "NIFTY", in_killzone: bool = True,
    liquidity_tolerance: float | None = None,
) -> dict[str, Any]:
    """Guardeer 11-lecture SMC profile: fractal HTF/MTF/LTF, structure,
    inducement proxy, OB/FVG POI, liquidity and intermediate/short-term swings.
    This is a transparent evidence profile, not a claim that every named block
    can be inferred from OHLC alone.
    """
    result = analyze_smc(htf_candles, mtf_candles, ltf_candles,
                         instrument=instrument, in_killzone=in_killzone,
                         liquidity_tolerance=liquidity_tolerance)
    htf_swings = find_swings(_valid(htf_candles))
    mtf_swings = find_swings(_valid(mtf_candles))
    ltf_swings = find_swings(_valid(ltf_candles))
    result["strategy_format"] = "Guardeer"
    result["format_modules"] = {
        "lecture_1": "Smart Money Concept",
        "lecture_2_fractal": {"htf": "1D", "mtf": "1H", "ltf": "15m", "available": bool(htf_swings and mtf_swings and ltf_swings)},
        "lecture_3_structure": {"bos": result["mtf"].get("bos", False), "choch": result["mtf"].get("choch", False), "inducement_proxy": mtf_swings[-2] if len(mtf_swings) >= 2 else None},
        "lecture_4_blocks_fvg": {"order_blocks": result["ltf"]["order_blocks"], "fvgs": result["ltf"]["fvgs"]},
        "lecture_5_liquidity": {"bsl": result["ltf"]["bsl"], "ssl": result["ltf"]["ssl"]},
        "lecture_6_poi": result["ltf"].get("poi"),
        "lecture_7_block_types": ["order_block", "breaker_block", "mitigation_block", "reclaimed_block", "rejection_block"],
        "lecture_8_swing_classes": {"ith_itl_sth_stl": "Requires confirmed nested swing hierarchy; not inferred from labels alone"},
        "lecture_9_bias": result["bias"],
        "lecture_10_timing": {"in_killzone": bool(in_killzone), "ote": "Calculated only when a valid dealing range is available"},
        "lecture_11_true_ict": {"htf_bias_mtf_structure_ltf_liquidity": True},
    }
    return result


def analyze_inner_circle(
    htf_candles: list[dict[str, Any]],
    mtf_candles: list[dict[str, Any]],
    ltf_candles: list[dict[str, Any]],
    *, instrument: str = "NIFTY", in_killzone: bool = True,
    liquidity_tolerance: float | None = None,
) -> dict[str, Any]:
    """Inner Circle ICT Core Course profile with bias, structure, liquidity,
    FVG/OB, OTE range, killzone and Power-of-3 evidence."""
    result = analyze_smc(htf_candles, mtf_candles, ltf_candles,
                         instrument=instrument, in_killzone=in_killzone,
                         liquidity_tolerance=liquidity_tolerance)
    htf = _valid(htf_candles)
    swing_high = max((c["high"] for c in htf), default=None)
    swing_low = min((c["low"] for c in htf), default=None)
    ote = None
    if swing_high is not None and swing_low is not None and swing_high > swing_low:
        span = swing_high - swing_low
        ote = {"62": swing_high - span * 0.62, "70.5": swing_high - span * 0.705, "79": swing_high - span * 0.79}
    result["strategy_format"] = "Inner Circle"
    result["format_modules"] = {
        "daily_weekly_bias": result["bias"],
        "market_structure": {"bos": result["mtf"].get("bos", False), "mss": result["mtf"].get("choch", False), "choch": result["mtf"].get("choch", False)},
        "liquidity": {"bsl": result["ltf"]["bsl"], "ssl": result["ltf"]["ssl"]},
        "fvg": result["ltf"]["fvgs"],
        "order_blocks": result["ltf"]["order_blocks"],
        "ote": ote,
        "killzone_filter": bool(in_killzone),
        "power_of_3": {"accumulation": None, "manipulation": None, "distribution": None, "note": "Session range/sweep data not supplied; AMD phases are not fabricated"},
    }
    return result
