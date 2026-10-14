"""Separate candle-close worker: idempotent Postgres persistence + engine event stream.

Run as a separate Railway service with start command:
    python -m app.engine_worker
Required environment: REDIS_URL and DATABASE_URL (or POSTGRES_URL).
This worker does not place or modify broker orders.
"""
from __future__ import annotations

import json
import os
import socket
import time
from typing import Any


STREAM = "chart:candle_closed"
GROUP = os.getenv("CHART_WORKER_GROUP", "chart-persistence-v1")
CONSUMER = os.getenv("CHART_WORKER_CONSUMER", socket.gethostname())
ENGINE_STREAM = "engine:candle_events"


def _clients():
    import redis
    import psycopg

    redis_url = os.getenv("REDIS_URL", "").strip()
    db_url = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    if not redis_url or not db_url:
        raise RuntimeError("REDIS_URL and DATABASE_URL (or POSTGRES_URL) are required")
    client = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=5)
    client.ping()
    conn = psycopg.connect(db_url, autocommit=True, connect_timeout=5)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS market_candles (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                candle_epoch BIGINT NOT NULL,
                open DOUBLE PRECISION NOT NULL,
                high DOUBLE PRECISION NOT NULL,
                low DOUBLE PRECISION NOT NULL,
                close DOUBLE PRECISION NOT NULL,
                volume DOUBLE PRECISION NOT NULL DEFAULT 0,
                source_seq BIGINT NOT NULL DEFAULT 0,
                persisted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (symbol, timeframe, candle_epoch)
            )
        """)
    return client, conn


def _persist(conn: Any, event: dict[str, Any], event_id: str) -> None:
    payload = json.loads(event["payload"])
    symbol, tf = str(payload["symbol"]), str(payload["tf"])
    candle_epoch = int(payload["t"])
    values = (
        symbol, tf, candle_epoch, float(payload["o"]), float(payload["h"]),
        float(payload["l"]), float(payload["c"]), float(payload.get("v") or 0),
        int(payload.get("seq") or 0),
    )
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO market_candles
                    (symbol, timeframe, candle_epoch, open, high, low, close, volume, source_seq)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (symbol, timeframe, candle_epoch) DO UPDATE SET
                    high = GREATEST(market_candles.high, EXCLUDED.high),
                    low = LEAST(market_candles.low, EXCLUDED.low),
                    close = EXCLUDED.close,
                    volume = GREATEST(market_candles.volume, EXCLUDED.volume),
                    source_seq = GREATEST(market_candles.source_seq, EXCLUDED.source_seq),
                    persisted_at = NOW()
            """, values)


def run() -> None:
    client, conn = _clients()
    try:
        try:
            client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        while True:
            batches = client.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=100, block=5000)
            for _, messages in batches:
                for message_id, fields in messages:
                    event_id = fields.get("event_id", message_id)
                    try:
                        _persist(conn, fields, event_id)
                        payload = json.loads(fields["payload"])
                        client.xadd(ENGINE_STREAM, {
                            "event_id": event_id,
                            "payload": json.dumps(payload, separators=(",", ":")),
                        }, maxlen=50000, approximate=True)
                        client.xack(STREAM, GROUP, message_id)
                    except Exception:
                        # Leave unacked for recovery; do not spin continuously on a poison message.
                        time.sleep(1)
    finally:
        conn.close()
        client.close()


if __name__ == "__main__":
    run()
