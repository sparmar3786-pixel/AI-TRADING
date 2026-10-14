from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.app import realtime_chart


class RealtimeChartTests(unittest.TestCase):
    def test_chart_key_normalizes_symbol_and_timeframe(self):
        self.assertEqual(realtime_chart._key('banknifty', '1m'), 'BANKNIFTY:1m')

    def test_chart_key_rejects_invalid_timeframe(self):
        with self.assertRaises(HTTPException) as ctx:
            realtime_chart._key('BANKNIFTY', '2s')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_snapshot_starts_with_empty_memory_cache(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('REDIS_URL', None)
            payload = asyncio.run(realtime_chart.candle_snapshot(symbol='BANKNIFTY', tf='1m', limit=10))
        self.assertEqual(payload['symbol'], 'BANKNIFTY')
        self.assertEqual(payload['tf'], '1m')
        self.assertEqual(payload['candles'], [])
        self.assertGreaterEqual(payload['seq'], 0)
        self.assertIn('ts_server', payload)
        self.assertEqual(payload['source'], 'memory')


if __name__ == '__main__':
    unittest.main()
