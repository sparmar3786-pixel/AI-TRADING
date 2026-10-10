"""Fail-closed risk checks. This module validates proposed orders; it never sends them."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class RiskLimits:
    max_risk_fraction: float = 0.01
    max_daily_loss_fraction: float = 0.03
    max_open_positions: int = 3
    max_order_notional_fraction: float = 0.25
    max_data_age_seconds: float = 30.0


def validate_proposed_order(*, equity, entry, stop, quantity, open_positions,
                            daily_pnl_fraction, data_age_seconds, limits=RiskLimits(),
                            kill_switch=False, is_paper=True):
    """Return {approved, reasons, risk_fraction, notional_fraction}; defaults fail closed."""
    reasons = []
    def number(name, value):
        try:
            result = float(value)
        except (TypeError, ValueError):
            reasons.append(name + "_INVALID")
            return None
        if not isfinite(result):
            reasons.append(name + "_INVALID")
            return None
        return result
    eq, ent, stp = number("EQUITY", equity), number("ENTRY", entry), number("STOP", stop)
    qty, daily, age = number("QUANTITY", quantity), number("DAILY_PNL", daily_pnl_fraction), number("DATA_AGE", data_age_seconds)
    if kill_switch:
        reasons.append("KILL_SWITCH_ACTIVE")
    if not is_paper:
        reasons.append("LIVE_EXECUTION_NOT_ENABLED_BY_THIS_MODULE")
    if eq is None or eq <= 0: reasons.append("EQUITY_MUST_BE_POSITIVE")
    if ent is None or ent <= 0: reasons.append("ENTRY_MUST_BE_POSITIVE")
    if stp is None or stp <= 0: reasons.append("STOP_MUST_BE_POSITIVE")
    if qty is None or qty <= 0 or (qty is not None and int(qty) != qty): reasons.append("QUANTITY_MUST_BE_POSITIVE_INTEGER")
    if ent is not None and stp is not None and ent == stp: reasons.append("STOP_MUST_DIFFER_FROM_ENTRY")
    if isinstance(open_positions, bool) or not isinstance(open_positions, int) or open_positions < 0:
        reasons.append("OPEN_POSITIONS_INVALID")
    elif open_positions >= limits.max_open_positions:
        reasons.append("MAX_OPEN_POSITIONS_REACHED")
    if daily is None or daily <= -limits.max_daily_loss_fraction:
        reasons.append("DAILY_LOSS_LIMIT_REACHED_OR_UNKNOWN")
    if age is None or age < 0 or age > limits.max_data_age_seconds:
        reasons.append("MARKET_DATA_STALE_OR_INVALID")
    risk_fraction = notional_fraction = None
    if eq and eq > 0 and ent and ent > 0 and stp and stp > 0 and qty and qty > 0:
        risk_fraction = abs(ent - stp) * qty / eq
        notional_fraction = ent * qty / eq
        if risk_fraction > limits.max_risk_fraction: reasons.append("PER_TRADE_RISK_LIMIT_EXCEEDED")
        if notional_fraction > limits.max_order_notional_fraction: reasons.append("ORDER_NOTIONAL_LIMIT_EXCEEDED")
    return {"approved": not reasons, "reasons": reasons, "risk_fraction": risk_fraction,
            "notional_fraction": notional_fraction, "mode": "PAPER_VALIDATION_ONLY"}
