"""Conservative risk sizing helpers for research and paper trading."""
from math import isfinite


def _positive(name, value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(name + " must be numeric") from None
    if not isfinite(n) or n <= 0:
        raise ValueError(name + " must be finite and > 0")
    return n


def position_size(equity, risk_fraction, entry, stop, lot_size=1, max_units=None):
    """Size units to a fixed equity risk budget; does not model fees, gaps or margin."""
    eq = _positive("equity", equity)
    risk = _positive("risk_fraction", risk_fraction)
    ent, stp = _positive("entry", entry), _positive("stop", stop)
    if risk >= 1:
        raise ValueError("risk_fraction must be < 1")
    if ent == stp:
        raise ValueError("entry and stop must differ")
    if not isinstance(lot_size, int) or lot_size < 1:
        raise ValueError("lot_size must be a positive integer")
    units = int((eq * risk) // abs(ent - stp))
    units = (units // lot_size) * lot_size
    if max_units is not None:
        if not isinstance(max_units, int) or max_units < 0:
            raise ValueError("max_units must be a non-negative integer")
        units = min(units, (max_units // lot_size) * lot_size)
    return units


def atr_stop_target(entry, atr_value, direction, stop_multiple=1.5, reward_risk=2.0):
    ent, a = _positive("entry", entry), _positive("atr_value", atr_value)
    sm, rr = _positive("stop_multiple", stop_multiple), _positive("reward_risk", reward_risk)
    side = str(direction).strip().upper()
    if side not in ("LONG", "SHORT"):
        raise ValueError("direction must be LONG or SHORT")
    distance = a * sm
    stop, target = ((ent-distance, ent+distance*rr) if side == "LONG"
                    else (ent+distance, ent-distance*rr))
    if stop <= 0 or target <= 0:
        raise ValueError("calculated levels must remain positive")
    return {"entry": ent, "stop": stop, "target": target,
            "risk_per_unit": distance, "reward_risk": rr}
