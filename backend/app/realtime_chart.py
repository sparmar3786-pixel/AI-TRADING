"""Low-latency candle snapshot/delta API.

Ticks are accepted from the backend market-feed adapter only. Redis is optional for
local development; production should set REDIS_URL and MARKET_INGEST_TOKEN.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["realtime-chart"])\n_async_redis_client = None\n_async_redis_lock = asyncio.Lock()
MAX_CANDLES = max(100, min(int(os.getenv("CHART_MAX_CANDLES", "2000")), 5000))
THROTTLE_SECONDS = max(0.1, min(float(os.getenv("CHART_DELTA_THROTTLE_MS", "200")) / 1000, 1.0))
_memory: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=MAX_CANDLES))
_current: dict[str, dict[str, Any]] = {}
_sequences: dict[str, int] = defaultdict(int)
_last_emit: dict[str, float] = defaultdict(float)
_lock = asyncio.Lock()


def _key(symbol: str, tf: str) -> str:
    symbol, tf = symbol.strip().upper(), tf.strip().lower()
    if not symbol or len(symbol) > 32 or not symbol.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")
    if tf not in {"1m", "3m", "5m", "15m", "30m", "1h", "1d"}:
        raise HTTPException(status_code=400, detail="Unsupported timeframe")
    return f"{symbol}:{tf}"


def _redis():
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis
        return redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    except Exception:
        return None

async def _async_redis():
    """Return one shared async Redis client for snapshot and WebSocket traffic."""
    global _async_redis_client
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    if _async_redis_client is not None:
        return _async_redis_client
    async with _async_redis_lock:
        if _async_redis_client is not None:
            return _async_redis_client
        try:
            from redis import asyncio as aioredis
            _async_redis_client = aioredis.Redis.from_url(
                url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1
            )
        except Exception:
            return None
        return _async_redis_client


@router.get("/snapshot")
async def candle_snapshot(symbol: str = Query("BANKNIFTY", max_length=32),
                          tf: str = Query("1m", max_length=8),
                          limit: int = Query(1000, ge=1, le=5000)) -> dict[str, Any]:
    key = _key(symbol, tf)
    redis_client = await _async_redis()
    if redis_client is not None:
        try:
            pipe = redis_client.pipeline(transaction=False)
            pipe.lrange(f"candles:{key}", -limit, -1)
            pipe.get(f"cur:{key}")
            pipe.get(f"seq:{key}")
            rows, cur, seq = await pipe.execute()
            candles = [json.loads(row) for row in rows]
            current = json.loads(cur) if cur else None
            return {"symbol": symbol.upper(), "tf": tf, "candles": candles,
                    "current": current, "seq": int(seq or 0), "ts_server": time.time(),
                    "source": "redis"}
        except Exception:
            pass
    async with _lock:
        candles = list(_memory[key])[-limit:]
        current = dict(_current[key]) if key in _current else None
        seq = _sequences[key]
    return {"symbol": symbol.upper(), "tf": tf, "candles": candles,
            "current": current, "seq": seq, "ts_server": time.time(),
            "source": "memory", "warning": "REDIS_URL not connected; data is process-local"}


@router.post("/internal/chart/tick")
async def ingest_chart_tick(payload: dict[str, Any],
                            authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Internal normalized tick/candle hook; do not expose without a strong secret."""
    token = os.getenv("MARKET_INGEST_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="MARKET_INGEST_TOKEN is not configured")
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    symbol = str(payload.get("symbol") or "BANKNIFTY")
    tf = str(payload.get("tf") or "1m")
    key = _key(symbol, tf)
    kind = str(payload.get("type") or "cur")
    now = time.time()
    allowed = {"t", "o", "h", "l", "c", "v", "seq", "type", "symbol", "tf"}
    data = {k: v for k, v in payload.items() if k in allowed}
    data["ts_server"] = now
    async with _lock:
        _sequences[key] += 1
        data["seq"] = _sequences[key]
        if kind == "new":
            prev = dict(_current.get(key) or {})
            if prev and prev.get("t") is not None:
                _memory[key].append(prev)
            _current[key] = data
        else:
            prev = dict(_current.get(key) or {})
            merged = {**prev, **data, "type": "cur"}
            _current[key] = merged
        current = dict(_current[key])
        seq = _sequences[key]
    redis_client = _redis()
    if redis_client is not None:
        try:
            def _write():
                pipe = redis_client.pipeline()
                pipe.set(f"cur:{key}", json.dumps(current, separators=(",", ":")))
                pipe.set(f"seq:{key}", seq)
                if kind == "new" and prev and prev.get("t") is not None:
                    pipe.rpush(f"candles:{key}", json.dumps(prev, separators=(",", ":")))
                    pipe.ltrim(f"candles:{key}", -MAX_CANDLES, -1)
                pipe.publish(f"chart.{symbol.upper()}.{tf}", json.dumps(current, separators=(",", ":")))
                pipe.execute()
            await asyncio.to_thread(_write)
        except Exception:
            pass
    return {"ok": True, "seq": seq, "ts_server": now, "current": current}


@router.websocket("/ws/chart")
async def chart_delta_socket(websocket: WebSocket) -> None:
    symbol = (websocket.query_params.get("symbol") or "BANKNIFTY").upper()
    tf = (websocket.query_params.get("tf") or "1m").lower()
    try:
        key = _key(symbol, tf)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    last_seq = int(websocket.query_params.get("lastSeq") or "0")
    redis_client = await _async_redis()
    pubsub = None
    try:
        if redis_client is not None:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(f"chart.{symbol}.{tf}")
        while True:
            sent = False
            if pubsub is not None:
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1), timeout=0.25
                    )
                    if message and message.get("type") == "message":
                        data = json.loads(message["data"])
                        seq = int(data.get("seq") or 0)
                        if seq > last_seq:
                            if last_seq and seq != last_seq + 1:
                                await websocket.send_json({"type": "gap", "expected": last_seq + 1,
                                                           "received": seq, "ts_server": time.time()})
                            await websocket.send_json(data)
                            last_seq, sent = seq, True
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass
                    pubsub = None
            if not sent:
                async with _lock:
                    current = dict(_current.get(key) or {})
                    seq = _sequences[key]
                if current and seq > last_seq and time.monotonic() - _last_emit[key] >= THROTTLE_SECONDS:
                    await websocket.send_json({**current, "ts_server": time.time()})
                    last_seq, sent = seq, True
                    _last_emit[key] = time.monotonic()
            if not sent:
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        if pubsub is not None:
            try:
                await pubsub.aclose()
            except Exception:
                pass
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass
