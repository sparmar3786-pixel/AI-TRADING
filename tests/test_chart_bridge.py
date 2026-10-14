from __future__ import annotations

import json

from integrations.chart_bridge import _symbols, publish_angelone_tick


def test_bridge_is_noop_without_redis(monkeypatch):
    monkeypatch.delenv('REDIS_URL', raising=False)
    monkeypatch.setattr('integrations.chart_bridge._client', None)
    publish_angelone_tick({'symbolToken': '123', 'ltp': 100.0, 'exchFeedTime': None})


def test_symbol_mapping_only_accepts_valid_symbols(monkeypatch):
    monkeypatch.setenv('CHART_TOKEN_SYMBOL_MAP', json.dumps({'123': 'BANKNIFTY', '456': 'NIFTY 50'}))
    assert _symbols() == {'123': 'BANKNIFTY'}
