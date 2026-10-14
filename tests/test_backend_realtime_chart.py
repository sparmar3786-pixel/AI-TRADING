from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from backend.app import realtime_chart


def test_chart_key_normalizes_symbol_and_timeframe():
    assert realtime_chart._key("banknifty", "1m") == "BANKNIFTY:1m"


def test_chart_key_rejects_invalid_timeframe():
    with pytest.raises(HTTPException) as exc:
        realtime_chart._key("BANKNIFTY", "2s")
    assert exc.value.status_code == 400


def test_snapshot_starts_with_empty_memory_cache(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    payload = asyncio.run(
        realtime_chart.candle_snapshot(symbol="BANKNIFTY", tf="1m", limit=10)
    )
    assert payload["symbol"] == "BANKNIFTY"
    assert payload["tf"] == "1m"
    assert payload["candles"] == []
    assert payload["seq"] >= 0
    assert "ts_server" in payload
    assert payload["source"] == "memory"
