"""Five-layer, fail-closed signal research engine for AI-TRADING.

This module consumes normalized market snapshots. It does not fetch broker data,
authenticate accounts, or place orders. Missing/stale evidence always returns WAIT.
Scores are evidence alignment, never a probability of profit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from math import isfinite
from typing import Any

from risk.position_sizing import atr_stop_target


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _timestamp(value: Any) -> datetime | None:
    """Normalize ISO strings and epoch seconds/milliseconds into UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and isfinite(float(value)):
        stamp = float(value)
        # Epoch milliseconds are currently 13 digits; seconds are 10 digits.
        if abs(stamp) >= 100_000_000_000:
            stamp /= 1000.0
        try:
            return datetime.fromtimestamp(stamp, timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _snapshot_timestamp(snapshot: dict[str, Any]) -> datetime | None:
    """Accept known timestamp aliases without treating receipt time as exchange time."""
    for key in ("observed_at", "source_timestamp", "exchange_timestamp", "timestamp", "time", "t"):
        if snapshot.get(key) is not None:
            parsed = _timestamp(snapshot.get(key))
            if parsed is not None:
                return parsed
    return None


def _age_seconds(now_utc: datetime, observed: datetime | None, *, future_skew_seconds: float = 2.0) -> float | None:
    if observed is None:
        return None
    age = (now_utc - observed).total_seconds()
    # Small device/exchange clock skew should not invalidate a fresh tick.
    if -future_skew_seconds <= age < 0:
        return 0.0
    return age


def _closes_direction(values: Any) -> str:
    if not isinstance(values, (list, tuple)) or len(values) < 3:
        return "UNKNOWN"
    numbers = [_number(item) for item in values[-5:]]
    if any(item is None or item <= 0 for item in numbers):
        return "UNKNOWN"
    clean = [float(item) for item in numbers]
    if clean[-1] > clean[-2] and clean[-1] > clean[0]:
        return "BULLISH"
    if clean[-1] < clean[-2] and clean[-1] < clean[0]:
        return "BEARISH"
    return "MIXED"


def evaluate_five_layer_signal(
    snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
    confirmation_state: dict[str, Any] | None = None,
    max_data_age_seconds: float = 15.0,
    confirmation_seconds: int = 600,
    max_confirmation_gap_seconds: int = 60,
) -> dict[str, Any]:
    """Evaluate data, trend/sentiment, order flow, option contract and risk/time gates.

    Expected snapshot keys:
      observed_at, underlying_ltp, sentiment_score (-1..1), timeframe_closes,
      order_flow {bid, ask, ltp, buy_volume, sell_volume},
      option_chain [{option_type, strike, expiry, bid, ask, ltp, volume, oi,
                     delta, option_atr, timestamp?}].
    The caller must provide exchange-validated, normalized inputs.
    """
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    layers: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []

    # Layer 1: data quality and freshness.
    observed = _snapshot_timestamp(snapshot)
    age = _age_seconds(now_utc, observed)
    underlying = _number(snapshot.get("underlying_ltp", snapshot.get("ltp", snapshot.get("price"))))
    if observed is None:
        data_reason_code, data_reason = "MISSING_OR_INVALID_TIMESTAMP", "No valid exchange/source timestamp (checked observed_at, source_timestamp, exchange_timestamp, timestamp, time, t)"
    elif age is not None and age < 0:
        data_reason_code, data_reason = "FUTURE_TIMESTAMP", "Market timestamp is more than 2 seconds ahead of server time"
    elif age is not None and age > max_data_age_seconds:
        data_reason_code, data_reason = "STALE_MARKET_DATA", f"Market snapshot is {age:.1f}s old; allowed maximum is {max_data_age_seconds:.1f}s"
    elif underlying is None or underlying <= 0:
        data_reason_code, data_reason = "INVALID_LTP", "Underlying LTP is missing, non-numeric, non-finite or not positive"
    else:
        data_reason_code, data_reason = "OK", "Timestamp and underlying LTP passed validation"
    data_ok = data_reason_code == "OK"
    layers["data_quality"] = {
        "pass": data_ok, "age_seconds": round(age, 2) if age is not None else None,
        "max_age_seconds": max_data_age_seconds,
        "source_timestamp": observed.isoformat() if observed else None,
        "reason_code": data_reason_code, "reason": data_reason,
    }
    if not data_ok:
        reasons.append(data_reason)

    # Layer 2: multi-timeframe trend + day/session sentiment alignment.
    raw_tfs = snapshot.get("timeframe_closes")
    raw_tfs = raw_tfs if isinstance(raw_tfs, dict) else {}
    trend_states = {str(tf): _closes_direction(closes) for tf, closes in raw_tfs.items()}
    directional = [state for state in trend_states.values() if state in ("BULLISH", "BEARISH")]
    trend = (
        "UNKNOWN" if len(directional) < 2 else
        "CONFLICT" if len(set(directional)) > 1 else directional[0]
    )
    sentiment = _number(snapshot.get("sentiment_score"))
    sentiment_ok = sentiment is not None and -1 <= sentiment <= 1
    sentiment_direction = (
        "BULLISH" if sentiment is not None and sentiment >= 0.2 else
        "BEARISH" if sentiment is not None and sentiment <= -0.2 else
        "NEUTRAL" if sentiment_ok else "UNKNOWN"
    )
    indicator_data = snapshot.get("indicators")
    indicator_data = indicator_data if isinstance(indicator_data, dict) else {}
    indicator_checks: dict[str, bool] = {}
    ema_fast = _number(indicator_data.get("ema_fast_8"))
    ema_slow = _number(indicator_data.get("ema_slow_21"))
    if ema_fast is not None and ema_slow is not None:
        ema_direction = "BULLISH" if ema_fast > ema_slow else "BEARISH" if ema_fast < ema_slow else "NEUTRAL"
        indicator_checks["ema_8_21_alignment"] = ema_direction == trend
    rsi = _number(indicator_data.get("rsi_14"))
    if rsi is not None:
        indicator_checks["rsi_not_extreme"] = not (
            (trend == "BULLISH" and rsi >= 75.0) or
            (trend == "BEARISH" and rsi <= 25.0)
        )
    macd_histogram = _number(indicator_data.get("macd_histogram"))
    if macd_histogram is not None:
        indicator_checks["macd_histogram_alignment"] = (
            macd_histogram > 0 if trend == "BULLISH" else
            macd_histogram < 0 if trend == "BEARISH" else False
        )
    vwap = _number(indicator_data.get("vwap"))
    underlying_for_vwap = _number(snapshot.get("underlying_ltp"))
    if vwap is not None and underlying_for_vwap is not None:
        indicator_checks["vwap_alignment"] = (
            underlying_for_vwap >= vwap if trend == "BULLISH" else
            underlying_for_vwap <= vwap if trend == "BEARISH" else False
        )
    indicators_ok = all(indicator_checks.values()) if indicator_checks else True
    layer2_ok = trend in ("BULLISH", "BEARISH") and sentiment_direction in (trend, "NEUTRAL") and indicators_ok
    layers["trend_sentiment"] = {
        "pass": layer2_ok, "trend": trend, "timeframes": trend_states,
        "sentiment_score": sentiment, "sentiment_direction": sentiment_direction,
        "indicator_checks": indicator_checks, "indicators_pass": indicators_ok,
    }
    if not layer2_ok:
        reasons.append("Trend and session sentiment are unknown, mixed or conflicting")

    # Layer 3: bid/ask sanity, spread and volume order-flow imbalance.
    flow = snapshot.get("order_flow")
    flow = flow if isinstance(flow, dict) else {}
    bid, ask, flow_ltp = map(_number, (flow.get("bid"), flow.get("ask"), flow.get("ltp")))
    # SmartAPI FULL-depth values are resting bid/ask book depth, not classified
    # executed buy/sell trade volume. Keep the two measures explicitly distinct.
    bid_depth, ask_depth = map(_number, (flow.get("bid_depth"), flow.get("ask_depth")))
    buy_vol, sell_vol = map(_number, (flow.get("buy_volume"), flow.get("sell_volume")))
    uses_book_depth = bid_depth is not None or ask_depth is not None
    if uses_book_depth:
        flow_left, flow_right = bid_depth, ask_depth
        flow_measure = "BOOK_DEPTH_IMBALANCE"
        flow_semantics = "bid_ask_depth_not_classified_trade_volume"
    else:
        flow_left, flow_right = buy_vol, sell_vol
        flow_measure = "TRADE_VOLUME_IMBALANCE"
        flow_semantics = "classified_executed_trade_volume"
    flow_valid = (
        bid is not None and ask is not None and flow_ltp is not None
        and 0 < bid <= flow_ltp <= ask
        and flow_left is not None and flow_right is not None
        and flow_left >= 0 and flow_right >= 0 and flow_left + flow_right > 0
    )
    spread_pct = ((ask - bid) / ((ask + bid) / 2) * 100) if flow_valid else None
    imbalance = ((flow_left - flow_right) / (flow_left + flow_right)) if flow_valid else None
    flow_direction = (
        "BULLISH" if imbalance is not None and imbalance >= 0.15 else
        "BEARISH" if imbalance is not None and imbalance <= -0.15 else
        "NEUTRAL" if imbalance is not None else "UNKNOWN"
    )
    layer3_ok = flow_valid and spread_pct is not None and spread_pct <= 2.0
    layers["order_flow"] = {
        "pass": bool(layer3_ok), "spread_pct": round(spread_pct, 3) if spread_pct is not None else None,
        "imbalance": round(imbalance, 3) if imbalance is not None else None,
        "direction": flow_direction, "measure": flow_measure, "semantics": flow_semantics,
    }
    if not layer3_ok:
        reasons.append("Order-flow quote is missing/invalid or spread exceeds 2%")
    if layer3_ok and flow_direction not in ("NEUTRAL", trend):
        layer3_ok = False
        layers["order_flow"]["pass"] = False
        reasons.append("Order flow conflicts with the trend")

    # Layer 4: choose a liquid, near-ATM option with sane bid/ask and usable delta.
    chain = snapshot.get("option_chain")
    chain = chain if isinstance(chain, list) else []
    option_type = "CALL" if trend == "BULLISH" else "PUT" if trend == "BEARISH" else None
    valid_options: list[tuple[float, dict[str, Any]]] = []
    for option in chain:
        if not isinstance(option, dict) or option.get("option_type", "").upper() != option_type:
            continue
        strike = _number(option.get("strike"))
        obid, oask, ltp = map(_number, (option.get("bid"), option.get("ask"), option.get("ltp")))
        volume, oi, delta = map(_number, (option.get("volume"), option.get("oi"), option.get("delta")))
        expiry_raw = str(option.get("expiry", "")).strip()
        expiry = None
        if expiry_raw:
            # Broker option-chain expiry is an exchange-local calendar date.
            # For NSE index options, treat that date as expiring at 15:30 IST,
            # not 23:59 UTC (which incorrectly keeps expired contracts eligible).
            try:
                expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
                expiry = datetime.combine(
                    expiry_date,
                    datetime.min.time().replace(hour=15, minute=30),
                    ZoneInfo("Asia/Kolkata"),
                ).astimezone(timezone.utc)
            except ValueError:
                expiry = _timestamp(expiry_raw)
        option_stamp = next((option.get(key) for key in ("timestamp", "source_timestamp", "exchange_timestamp", "time", "t") if option.get(key) is not None), None)
        option_time = _timestamp(option_stamp) if option_stamp is not None else observed
        option_age = _age_seconds(now_utc, option_time)
        valid = (
            strike is not None and strike > 0 and obid is not None and oask is not None
            and ltp is not None and 0 < obid <= ltp <= oask
            and volume is not None and volume > 0 and oi is not None and oi > 0
            and delta is not None and 0.25 <= abs(delta) <= 0.75
            and expiry is not None and expiry > now_utc
            and option_age is not None and 0 <= option_age <= max_data_age_seconds
        )
        if not valid:
            continue
        option_spread = (oask - obid) / ((oask + obid) / 2) * 100
        if option_spread > 5.0:
            continue
        # Prefer near ATM and moderate absolute delta, then liquid contracts.
        score = abs(strike - float(underlying or 0)) / max(float(underlying or 1), 1) * 100
        score += abs(abs(delta) - 0.5) * 2
        score -= min(volume, 1_000_000) / 1_000_000 * 0.05
        valid_options.append((score, option))
    selected = min(valid_options, key=lambda pair: pair[0])[1] if valid_options else None
    layer4_ok = selected is not None
    layers["option_selection"] = {
        "pass": layer4_ok, "option_type": option_type,
        "candidate_count": len(valid_options),
        "strike": selected.get("strike") if selected else None,
        "expiry": selected.get("expiry") if selected else None,
        "spread_pct": round((float(selected["ask"]) - float(selected["bid"])) /
                            ((float(selected["ask"]) + float(selected["bid"])) / 2) * 100, 3)
                       if selected else None,
    }
    if not layer4_ok:
        reasons.append("No fresh, liquid, non-expired option contract passes spread/delta checks")

    # Layer 5: risk levels + ten-minute stable-candidate gate.
    entry = _number(selected.get("ask")) if selected else None
    option_atr = _number(selected.get("option_atr")) if selected else None
    risk_ok = (
        entry is not None and entry > 0 and option_atr is not None and option_atr > 0
    )
    stop = target = None
    if risk_ok and entry is not None and option_atr is not None:
        risk_distance = 1.5 * option_atr
        stop, target = entry - risk_distance, entry + 2 * risk_distance
        if stop <= 0:
            risk_ok = False
            stop = target = None
    layers["risk_levels"] = {
        "pass": risk_ok, "entry_reference": entry,
        "stop_loss": round(stop, 4) if stop is not None else None,
        "target": round(target, 4) if target is not None else None,
        "reward_risk": 2.0 if risk_ok else None,
        "method": "1.5 x option ATR stop; 2R target; excludes costs/slippage",
    }
    if not risk_ok:
        reasons.append("Option ATR or valid positive risk levels are missing")

    all_layers_pass = data_ok and layer2_ok and layer3_ok and layer4_ok and risk_ok
    candidate = None
    if all_layers_pass and selected:
        candidate = f"{option_type}|{selected.get('strike')}|{selected.get('expiry')}"
    state = confirmation_state if isinstance(confirmation_state, dict) else {}
    since = _timestamp(state.get("since_utc"))
    last_seen = _timestamp(state.get("last_seen_utc"))
    state_key_matches = candidate is not None and state.get("candidate_key") == candidate
    gap = (now_utc - last_seen).total_seconds() if last_seen else None
    if not all_layers_pass or candidate is None:
        new_state = {}
        decision = "WAIT"
        stability = "BLOCKED"
    elif not state_key_matches or since is None or last_seen is None or gap is None or gap < 0 or gap > max_confirmation_gap_seconds:
        new_state = {"candidate_key": candidate, "since_utc": now_utc.isoformat(), "last_seen_utc": now_utc.isoformat()}
        decision = "WAIT"
        stability = "CONFIRMING"
        reasons.append("New candidate or refresh gap: restarting 10-minute confirmation")
    else:
        new_state = {"candidate_key": candidate, "since_utc": since.isoformat(), "last_seen_utc": now_utc.isoformat()}
        elapsed = (now_utc - since).total_seconds()
        if elapsed < confirmation_seconds:
            decision = "WAIT"
            stability = "CONFIRMING"
            reasons.append(f"Candidate stability gate: {int(confirmation_seconds - elapsed)} seconds remaining")
        else:
            decision = "CALL BUY" if option_type == "CALL" else "PUT BUY"
            stability = "CONFIRMED"

    layers["confirmation"] = {
        "pass": decision in ("CALL BUY", "PUT BUY"),
        "state": stability, "required_seconds": confirmation_seconds,
    }
    return {
        "decision": decision,
        "candidate_decision": ("CALL BUY" if option_type == "CALL" else "PUT BUY") if candidate else "WAIT",
        "underlying_ltp": underlying,
        "option_type": option_type if candidate else None,
        "strike": selected.get("strike") if candidate and selected else None,
        "expiry": selected.get("expiry") if candidate and selected else None,
        "entry": round(entry, 4) if candidate and entry is not None else None,
        "stop_loss": round(stop, 4) if candidate and stop is not None else None,
        "target": round(target, 4) if candidate and target is not None else None,
        "layers": layers,
        "reasons": reasons,
        "confirmation_state": new_state,
        "score_semantics": "Layer pass status is a rule checklist, not probability of profit",
        "signal_only": True,
    }


def evaluate_futures_signal(
    snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
    confirmation_state: dict[str, Any] | None = None,
    max_data_age_seconds: float = 60.0,
    confirmation_seconds: int = 600,
    max_confirmation_gap_seconds: int = 60,
) -> dict[str, Any]:
    """Five-layer read-only signal evaluator for liquid MCX futures.

    Futures use the underlying ATR and a 2R target; no option strike is fabricated.
    """
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reasons: list[str] = []
    layers: dict[str, dict[str, Any]] = {}

    observed = _snapshot_timestamp(snapshot)
    age = _age_seconds(now_utc, observed)
    ltp = _number(snapshot.get("underlying_ltp", snapshot.get("ltp", snapshot.get("price"))))
    if observed is None:
        data_reason_code, data_reason = "MISSING_OR_INVALID_TIMESTAMP", "No valid exchange/source timestamp (checked observed_at, source_timestamp, exchange_timestamp, timestamp, time, t)"
    elif age is not None and age < 0:
        data_reason_code, data_reason = "FUTURE_TIMESTAMP", "Commodity timestamp is more than 2 seconds ahead of server time"
    elif age is not None and age > max_data_age_seconds:
        data_reason_code, data_reason = "STALE_MARKET_DATA", f"Commodity quote is {age:.1f}s old; allowed maximum is {max_data_age_seconds:.1f}s"
    elif ltp is None or ltp <= 0:
        data_reason_code, data_reason = "INVALID_LTP", "Commodity LTP is missing, non-numeric, non-finite or not positive"
    else:
        data_reason_code, data_reason = "OK", "Timestamp and commodity LTP passed validation"
    data_ok = data_reason_code == "OK"
    layers["data_quality"] = {"pass": data_ok, "age_seconds": round(age, 2) if age is not None else None, "max_age_seconds": max_data_age_seconds, "source_timestamp": observed.isoformat() if observed else None, "reason_code": data_reason_code, "reason": data_reason}
    if not data_ok:
        reasons.append(data_reason)

    raw_tfs = snapshot.get("timeframe_closes")
    raw_tfs = raw_tfs if isinstance(raw_tfs, dict) else {}
    timeframe_states = {str(tf): _closes_direction(values) for tf, values in raw_tfs.items()}
    directional = [value for value in timeframe_states.values() if value in ("BULLISH", "BEARISH")]
    trend = "UNKNOWN" if len(directional) < 2 else "CONFLICT" if len(set(directional)) > 1 else directional[0]
    sentiment = _number(snapshot.get("sentiment_score"))
    sentiment_direction = "BULLISH" if sentiment is not None and sentiment >= 0.2 else "BEARISH" if sentiment is not None and sentiment <= -0.2 else "NEUTRAL" if sentiment is not None and -1 <= sentiment <= 1 else "UNKNOWN"
    indicators = snapshot.get("indicators") if isinstance(snapshot.get("indicators"), dict) else {}
    checks: dict[str, bool] = {}
    fast, slow = _number(indicators.get("ema_fast_8")), _number(indicators.get("ema_slow_21"))
    if fast is not None and slow is not None:
        checks["ema_alignment"] = ("BULLISH" if fast > slow else "BEARISH" if fast < slow else "NEUTRAL") == trend
    rsi = _number(indicators.get("rsi_14"))
    if rsi is not None:
        checks["rsi_not_extreme"] = not ((trend == "BULLISH" and rsi >= 75) or (trend == "BEARISH" and rsi <= 25))
    macd = _number(indicators.get("macd_histogram"))
    if macd is not None:
        checks["macd_alignment"] = macd > 0 if trend == "BULLISH" else macd < 0 if trend == "BEARISH" else False
    vwap = _number(indicators.get("vwap"))
    if vwap is not None and ltp is not None:
        checks["vwap_alignment"] = ltp >= vwap if trend == "BULLISH" else ltp <= vwap if trend == "BEARISH" else False
    indicators_ok = all(checks.values()) if checks else True
    layer2_ok = trend in ("BULLISH", "BEARISH") and sentiment_direction in (trend, "NEUTRAL") and indicators_ok
    layers["trend_sentiment"] = {
        "pass": layer2_ok, "trend": trend, "timeframes": timeframe_states,
        "sentiment_score": sentiment, "sentiment_direction": sentiment_direction,
        "indicator_checks": checks, "indicators_pass": indicators_ok,
    }
    if not layer2_ok:
        reasons.append("Commodity trend, indicators or session sentiment are conflicting")

    flow = snapshot.get("order_flow") if isinstance(snapshot.get("order_flow"), dict) else {}
    bid, ask, flow_ltp = map(_number, (flow.get("bid"), flow.get("ask"), flow.get("ltp")))
    buy_volume, sell_volume = map(_number, (flow.get("buy_volume"), flow.get("sell_volume")))
    flow_ok = (
        bid is not None and ask is not None and bid > 0 and ask > bid
        and flow_ltp is not None and bid <= flow_ltp <= ask
        and buy_volume is not None and sell_volume is not None
        and buy_volume + sell_volume > 0
        and ((buy_volume >= sell_volume) if trend == "BULLISH" else (sell_volume >= buy_volume) if trend == "BEARISH" else False)
    )
    spread_pct = ((ask - bid) / ((ask + bid) / 2) * 100) if bid is not None and ask is not None and ask > bid else None
    flow_ok = flow_ok and spread_pct is not None and spread_pct <= 0.5
    layers["order_flow"] = {"pass": flow_ok, "bid": bid, "ask": ask, "spread_pct": round(spread_pct, 4) if spread_pct is not None else None, "buy_volume": buy_volume, "sell_volume": sell_volume}
    if not flow_ok:
        reasons.append("Commodity bid/ask, depth imbalance or spread does not pass the execution gate")

    contract = snapshot.get("contract") if isinstance(snapshot.get("contract"), dict) else {}
    volume, oi, lot_size = map(_number, (contract.get("volume"), contract.get("oi"), contract.get("lot_size")))
    expiry_text = str(contract.get("expiry") or "")
    expiry = _timestamp(expiry_text + "T23:59:00+00:00") if expiry_text else None
    contract_ok = volume is not None and volume > 0 and oi is not None and oi > 0 and lot_size is not None and lot_size > 0 and expiry is not None and expiry > now_utc
    layers["contract_selection"] = {"pass": contract_ok, "symbol": contract.get("symbol"), "expiry": expiry_text or None, "volume": volume, "oi": oi, "lot_size": lot_size, "spread_pct": round(spread_pct, 4) if spread_pct is not None else None}
    if not contract_ok:
        reasons.append("Active commodity contract lacks valid expiry, volume, OI or lot size")

    atr = _number(indicators.get("underlying_atr_14"))
    entry = ask if trend == "BULLISH" else bid if trend == "BEARISH" else None
    risk_distance = 1.5 * atr if atr is not None and atr > 0 else None
    stop = target = None
    if entry is not None and risk_distance is not None:
        try:
            levels = atr_stop_target(entry, atr, "LONG" if trend == "BULLISH" else "SHORT", stop_multiple=1.5, reward_risk=2.0)
            stop, target = levels["stop"], levels["target"]
            risk_distance = levels["risk_per_unit"]
        except ValueError:
            stop = target = None
            risk_distance = None
    risk_ok = entry is not None and entry > 0 and stop is not None and target is not None and stop > 0 and target > 0 and risk_distance is not None
    layers["risk_levels"] = {
        "pass": risk_ok, "entry_reference": entry,
        "stop_loss": round(stop, 4) if stop is not None else None,
        "target": round(target, 4) if target is not None else None,
        "reward_risk": 2.0 if risk_ok else None,
        "method": "1.5 x underlying ATR stop; 2R target; signal only",
    }
    if not risk_ok:
        reasons.append("Commodity ATR or valid positive stop/target levels are missing")

    all_pass = data_ok and layer2_ok and flow_ok and contract_ok and risk_ok
    side = "BUY FUTURE" if trend == "BULLISH" else "SELL FUTURE" if trend == "BEARISH" else None
    candidate = f"{contract.get('symbol')}|{contract.get('expiry')}|{side}" if all_pass and side else None
    state = confirmation_state if isinstance(confirmation_state, dict) else {}
    since, last_seen = _timestamp(state.get("since_utc")), _timestamp(state.get("last_seen_utc"))
    gap = (now_utc - last_seen).total_seconds() if last_seen else None
    matches = candidate is not None and state.get("candidate_key") == candidate
    if not all_pass or candidate is None:
        new_state, decision, stability = {}, "WAIT", "BLOCKED"
    elif not matches or since is None or last_seen is None or gap is None or gap < 0 or gap > max_confirmation_gap_seconds:
        new_state = {"candidate_key": candidate, "since_utc": now_utc.isoformat(), "last_seen_utc": now_utc.isoformat()}
        decision, stability = "WAIT", "CONFIRMING"
        reasons.append("New commodity candidate or refresh gap: restarting 10-minute confirmation")
    else:
        elapsed = (now_utc - since).total_seconds()
        new_state = {"candidate_key": candidate, "since_utc": since.isoformat(), "last_seen_utc": now_utc.isoformat()}
        if elapsed < confirmation_seconds:
            decision, stability = "WAIT", "CONFIRMING"
            reasons.append(f"Commodity signal stability gate: {int(confirmation_seconds - elapsed)} seconds remaining")
        else:
            decision, stability = side, "CONFIRMED"
    layers["confirmation"] = {"pass": decision in ("BUY FUTURE", "SELL FUTURE"), "state": stability, "required_seconds": confirmation_seconds}
    return {
        "decision": decision, "candidate_decision": side if candidate else "WAIT",
        "direction": trend, "entry": round(entry, 4) if candidate and entry is not None else None,
        "stop_loss": round(stop, 4) if candidate and stop is not None else None,
        "target": round(target, 4) if candidate and target is not None else None,
        "layers": layers, "reasons": reasons, "confirmation_state": new_state,
        "signal_stability": {"state": stability, "required_minutes": 10, "required_seconds": confirmation_seconds},
        "signal_only": True, "order_placement_enabled": False,
    }
