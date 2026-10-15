"""Small, bounded PostgreSQL state store used to survive Railway redeploys.

Only application JSON state is stored here; sensitive Angel One credentials are
stored as an already-encrypted AES-GCM blob. All failures are fail-soft so the
API can continue using the mounted-volume fallback while a database is offline.
"""
from __future__ import annotations

import os
import threading
from typing import Any

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _database_url() -> str:
    return (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()


def database_configured() -> bool:
    return bool(_database_url())


def _connect():
    url = _database_url()
    if not url:
        return None
    try:
        import psycopg
        from psycopg.types.json import Jsonb
        connection = psycopg.connect(
            url,
            connect_timeout=2,
            options="-c statement_timeout=2000",
            autocommit=True,
        )
        global _SCHEMA_READY
        if not _SCHEMA_READY:
            with _SCHEMA_LOCK:
                if not _SCHEMA_READY:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS ai_trading_state ("
                        "state_key TEXT PRIMARY KEY, "
                        "state_json JSONB NOT NULL, "
                        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
                    )
                    _SCHEMA_READY = True
        return connection
    except Exception:
        return None


def get_state(key: str) -> tuple[bool, Any]:
    """Return (database_reachable, value); None means no row when reachable."""
    connection = _connect()
    if connection is None:
        return False, None
    try:
        with connection:
            row = connection.execute(
                "SELECT state_json FROM ai_trading_state WHERE state_key = %s",
                (key,),
            ).fetchone()
        return True, row[0] if row else None
    except Exception:
        return False, None
    finally:
        connection.close()


def put_state(key: str, value: Any) -> bool:
    connection = _connect()
    if connection is None:
        return False
    try:
        with connection:
            connection.execute(
                "INSERT INTO ai_trading_state (state_key, state_json, updated_at) "
                "VALUES (%s, %s, NOW()) "
                "ON CONFLICT (state_key) DO UPDATE SET "
                "state_json = EXCLUDED.state_json, updated_at = NOW()",
                (key, Jsonb(value)),
            )
        return True
    except Exception:
        return False
    finally:
        connection.close()


def delete_state(key: str) -> tuple[bool, bool]:
    """Return (database_reachable, row_deleted)."""
    connection = _connect()
    if connection is None:
        return False, False
    try:
        with connection:
            cursor = connection.execute(
                "DELETE FROM ai_trading_state WHERE state_key = %s",
                (key,),
            )
            return True, cursor.rowcount > 0
    except Exception:
        return False, False
    finally:
        connection.close()
