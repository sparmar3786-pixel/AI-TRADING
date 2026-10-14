"""Non-blocking bridge from normalized Angel One ticks to Redis candle streams.

Configure CHART_TOKEN_SYMBOL_MAP as JSON, e.g. {"99926000":"NIFTY"}.
Redis is required for cross-process snapshots and delta delivery; this bridge
fails closed (does not fabricate candles) when Redis is not configured.
"""
from __future__ import annotations

import json
import os
import queue
import threading
from datetime import datetime, timezone
from typing import Any

_client = None
_client_lock = threading.Lock()
_volume_by_token: dict[str, float] = {}
_state_lock = threading.RLock()
_current_by_key: dict[str, dict[str, Any]] = {}
_sequence_by_key: dict[str, int] = {}
_loaded_keys: set[str] = {}
_volume_lock = threading.Lock()
_tick_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=4096)
_worker_lock = threading.Lock()
_worker_started = False
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


def _process_tick(tick: dict[str, Any]) -> None:
    """Update candles in memory and batch Redis writes once per incoming tick."""
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
    # The chart bridge has one worker in this process. Load each candle and
    # sequence once, then avoid Redis GET/INCR round-trips on every market tick.
    pipe = client.pipeline(transaction=True)
    writes = 0
    for tf, seconds in TIMEFRAMES.items():
        key = f"{symbol}:{tf}"
        bucket = now_epoch - (now_epoch % seconds)
        current_key = f"cur:{key}"
        with _state_lock:
            current = _current_by_key.get(key)
            if key not in _loaded_keys:
                raw, raw_seq = client.mget(current_key, f"seq:{key}")
                try:
                    restored = json.loads(raw) if raw else None
                except (TypeError, ValueError):
                    restored = None
                current = restored if isinstance(restored, dict) else None
                try:
                    _sequence_by_key[key] = int(raw_seq or (current or {}).get("seq") or 0)
                except (TypeError, ValueError):
                    _sequence_by_key[key] = int((current or {}).get("seq") or 0)
                _loaded_keys.add(key)
                if current is not None:
                    _current_by_key[key] = current
            if not isinstance(current, dict) or int(current.get("t", -1)) != bucket:
                if isinstance(current, dict) and current.get("t") is not None:
                    closed = {**current, "type": "closed"}
                    encoded_closed = json.dumps(closed, separators=(",", ":"))
                    pipe.rpush(f"candles:{key}", encoded_closed)
                    pipe.ltrim(f"candles:{key}", -max(100, min(int(os.getenv("CHART_MAX_CANDLES", "2000")), 5000)), -1)
                    pipe.xadd("chart:candle_closed", {"payload": encoded_closed,
                        "event_id": f"{symbol}:{tf}:{current.get('t')}"}, maxlen=50000, approximate=True)
                current = {"t": bucket, "o": float(price), "h": float(price),
                           "l": float(price), "c": float(price), "v": delta_volume,
                           "type": "new", "symbol": symbol, "tf": tf}
            else:
                current = {**current, "h": max(float(current.get("h", price)), float(price)),
                           "l": min(float(current.get("l", price)), float(price)),
                           "c": float(price), "v": float(current.get("v", 0)) + delta_volume,
                           "type": "cur", "symbol": symbol, "tf": tf}
            _sequence_by_key[key] = _sequence_by_key.get(key, 0) + 1
            current["seq"] = _sequence_by_key[key]
            current["ts_server"] = datetime.now(timezone.utc).timestamp()
            _current_by_key[key] = current
            encoded = json.dumps(current, separators=(",", ":"))
        pipe.set(current_key, encoded)
        pipe.set(f"seq:{key}", current["seq"])
        pipe.publish(f"chart.{symbol}.{tf}", encoded)
        writes += 1
    if writes:
        pipe.execute()

def _worker() -> None:
    while True:
        tick = _tick_queue.get()
        try:
            _process_tick(tick)
        except Exception:
            # Chart analytics are best-effort and must not terminate the worker.
            pass
        finally:
            _tick_queue.task_done()


def publish_angelone_tick(tick: dict[str, Any]) -> None:
    """Queue chart processing so Redis/network work never blocks SmartAPI callbacks."""
    global _worker_started
    if not os.getenv("REDIS_URL", "").strip():
        return
    with _worker_lock:
        if not _worker_started:
            threading.Thread(target=_worker, name="angelone-chart-bridge", daemon=True).start()
            _worker_started = True
    try:
        _tick_queue.put_nowait(dict(tick))
    except queue.Full:
        # Drop the oldest queued tick to preserve freshness over stale backlog.
        try:
            _tick_queue.get_nowait()
            _tick_queue.task_done()
        except queue.Empty:
            pass
        try:
            _tick_queue.put_nowait(dict(tick))
        except queue.Full:
            pass
