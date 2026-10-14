"""Non-blocking bridge from normalized Angel One ticks to Redis candle streams.

Configure CHART_TOKEN_SYMBOL_MAP as JSON, e.g. {"99926000":"NIFTY"}.
Redis is required for cross-process snapshots and delta delivery; this bridge
fails closed (does not fabricate candles) when Redis is not configured.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

_client = None
_client_lock = threading.Lock()
_volume_by_token: dict[str, float] = {}
_volume_lock = threading.Lock()
TIMEFRAMES = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400}


def _redis():
    global _client
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    with _client_lock:
        if _client is None:
            try:
                import redis
                _client = redis.Redis.from_url(
                    url, decode_responses=True, socket_connect_timeout=1,
                    socket_timeout=1, health_check_interval=30,
                )
            except Exception:
                return None
        return _client


def _symbols() -> dict[str, str]:
    try:
        raw = json.loads(os.getenv("CHART_TOKEN_SYMBOL_MAP", "{}"))
        if not isinstance(raw, dict):
            return {}
        return {str(token).strip(): str(symbol).strip().upper()
                for token, symbol in raw.items()
                if str(token).strip() and str(symbol).strip()
                and str(symbol).replace("_", "").isalnum()
                and len(str(symbol)) <= 32}
    except (TypeError, ValueError):
        return {}


def publish_angelone_tick(tick: dict[str, Any]) -> None:
    """Turn one normalized Angel One tick into Redis OHLCV updates."""
    client = _redis()
    if client is None:
        return
    token = str(tick.get("symbolToken") or "").strip()
    symbol = _symbols().get(token)
    price = tick.get("ltp")
    if not symbol or not isinstance(price, (int, float)) or price <= 0:
        return
    stamp = tick.get("exchFeedTime")
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")) if stamp else datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        dt = datetime.now(timezone.utc)
    cumulative = tick.get("tradeVolume")
    with _volume_lock:
        prior_volume = _volume_by_token.get(token)
        try:
            cumulative_num = float(cumulative) if cumulative is not None else None
        except (TypeError, ValueError):
            cumulative_num = None
        delta_volume = 0.0
        if cumulative_num is not None and cumulative_num >= 0:
            if prior_volume is not None and cumulative_num >= prior_volume:
                delta_volume = cumulative_num - prior_volume
            _volume_by_token[token] = cumulative_num

    now_epoch = int(dt.timestamp())
    pipe = client.pipeline(transaction=True)
    updates = []
    for tf, seconds in TIMEFRAMES.items():
        key = f"{symbol}:{tf}"
        bucket = now_epoch - (now_epoch % seconds)
        current_key = f"cur:{key}"
        raw = client.get(current_key)
        try:
            current = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            current = None
        if not isinstance(current, dict) or int(current.get("t", -1)) != bucket:
            if isinstance(current, dict) and current.get("t") is not None:
                pipe.rpush(f"candles:{key}", json.dumps(current, separators=(",", ":")))
                pipe.ltrim(f"candles:{key}", -max(100, min(int(os.getenv("CHART_MAX_CANDLES", "2000")), 5000)), -1)
            current = {"t": bucket, "o": float(price), "h": float(price),
                       "l": float(price), "c": float(price), "v": delta_volume,
                       "type": "new", "symbol": symbol, "tf": tf}
        else:
            current = {**current, "h": max(float(current.get("h", price)), float(price)),
                       "l": min(float(current.get("l", price)), float(price)),
                       "c": float(price), "v": float(current.get("v", 0)) + delta_volume,
                       "type": "cur", "symbol": symbol, "tf": tf}
        seq = int(client.incr(f"seq:{key}"))
        current["seq"] = seq
        current["ts_server"] = datetime.now(timezone.utc).timestamp()
        pipe.set(current_key, json.dumps(current, separators=(",", ":")))
        pipe.publish(f"chart.{symbol}.{tf}", json.dumps(current, separators=(",", ":")))
        updates.append((key, current))
    pipe.execute()
