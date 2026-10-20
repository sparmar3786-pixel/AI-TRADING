"""Fail-closed safety helpers for paper-trading integrations.

These helpers are intentionally not an execution engine. Callers must keep the
public signal at WAIT when data validation fails, and must reconcile broker
orders/positions independently before enabling live execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

import pandas as pd

_CANDLE_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class MarketDataError(ValueError):
    """Raised when a broker response cannot be safely normalized."""


def normalize_smartapi_candles(response: Mapping[str, Any]) -> pd.DataFrame:
    """Normalize common SmartAPI candle payload shapes or fail closed."""
    data = response.get("data")
    rows = data.get("candles") if isinstance(data, Mapping) else data
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise MarketDataError("SmartAPI returned no candle rows")

    normalized: list[list[Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            values = [row.get(k) for k in _CANDLE_COLUMNS]
        elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
            if len(row) < 6:
                raise MarketDataError("Candle row has fewer than six fields")
            values = list(row[:6])
        else:
            raise MarketDataError("Unsupported candle row shape")
        normalized.append(values)

    frame = pd.DataFrame(normalized, columns=_CANDLE_COLUMNS)
    raw_ts = frame["timestamp"].copy()

    def parse_timestamp(value: Any) -> pd.Timestamp:
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            unit = "ms" if abs(float(value)) >= 100_000_000_000 else "s"
            return pd.to_datetime(value, unit=unit, utc=True)
        # Numeric timestamp strings should not be interpreted as calendar dates.
        if isinstance(value, str) and value.strip().isdigit():
            numeric = int(value.strip())
            unit = "ms" if abs(numeric) >= 100_000_000_000 else "s"
            return pd.to_datetime(numeric, unit=unit, utc=True)
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(parsed):
            raise MarketDataError("Candle timestamp is invalid")
        return parsed

    frame["timestamp"] = raw_ts.map(parse_timestamp)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    numeric = frame[["open", "high", "low", "close", "volume"]]
    if numeric.isna().any().any():
        raise MarketDataError("Candle contains missing or non-numeric OHLCV values")
    if not all(math.isfinite(float(v)) for v in numeric.to_numpy().ravel()):
        raise MarketDataError("Candle contains non-finite OHLCV values")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any() or (frame["volume"] < 0).any():
        raise MarketDataError("Candle contains invalid prices or negative volume")
    if (frame["high"] < frame[["open", "low", "close"]].max(axis=1)).any():
        raise MarketDataError("Candle high is below open/low/close")
    if (frame["low"] > frame[["open", "high", "close"]].min(axis=1)).any():
        raise MarketDataError("Candle low is above open/high/close")

    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    frame = frame.set_index("timestamp")
    if frame.empty:
        raise MarketDataError("No valid candles remain after normalization")
    return frame


def floor_to_lot(quantity: int, lot_size: int) -> int:
    """Round a non-negative quantity down to a whole lot; invalid sizes fail."""
    if (isinstance(quantity, bool) or isinstance(lot_size, bool)
            or not isinstance(quantity, int) or not isinstance(lot_size, int)
            or quantity < 0 or lot_size <= 0):
        raise ValueError("quantity must be an integer >= 0 and lot_size an integer > 0")
    return (quantity // lot_size) * lot_size


def target_exit_quantity(original_quantity: int, already_exited: int,
                         target_percent: float, lot_size: int) -> int:
    """Compute one exit tranche as a percentage of ORIGINAL quantity.

    The result is lot-aligned and capped by remaining quantity. A zero result
    means no valid lot can be exited; callers must not mark the target complete.
    """
    if (isinstance(original_quantity, bool) or isinstance(already_exited, bool)
            or not isinstance(original_quantity, int) or not isinstance(already_exited, int)
            or original_quantity < 0 or already_exited < 0
            or already_exited > original_quantity):
        raise ValueError("invalid original/already-exited quantity")
    if not math.isfinite(target_percent) or not 0 < target_percent <= 100:
        raise ValueError("target_percent must be in (0, 100]")
    lot_aligned_original = floor_to_lot(original_quantity, lot_size)
    remaining = floor_to_lot(original_quantity - already_exited, lot_size)
    tranche = floor_to_lot(math.floor(lot_aligned_original * target_percent / 100), lot_size)
    return min(remaining, tranche)


def unrealized_pnl(entry_price: float, mark_price: float, quantity: int,
                   side: str) -> float:
    """Calculate mark-to-market P&L from the traded instrument's prices."""
    values = (entry_price, mark_price)
    if (any(not math.isfinite(v) or v <= 0 for v in values)
            or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0):
        raise ValueError("prices must be finite/positive and quantity a non-negative integer")
    normalized_side = side.strip().upper()
    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    direction = 1 if normalized_side == "BUY" else -1
    return (mark_price - entry_price) * quantity * direction


def require_fresh_quote(timestamp: datetime, now: datetime, max_age_seconds: float) -> None:
    """Raise when a quote is future-dated or older than the configured limit."""
    if timestamp.tzinfo is None or now.tzinfo is None:
        raise ValueError("quote and current timestamps must be timezone-aware")
    if not math.isfinite(max_age_seconds) or max_age_seconds < 0:
        raise ValueError("max_age_seconds must be finite and non-negative")
    age = (now.astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise MarketDataError("Quote is stale or future-dated")
