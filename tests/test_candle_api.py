import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app import main as api


class CandleHistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.headers = {"X-Device-Id": "A" * 43}

    def test_candle_endpoint_returns_only_validated_broker_rows(self):
        class FakeAdapter:
            def candles(self, exchange, token, interval, fromdate, todate):
                return {"candles": [
                    ["2026-10-14 09:15", 100, 105, 99, 102, 1000],
                    ["2026-10-14 09:20", 102, 106, 101, 104, 1200],
                    # Invalid OHLC relationship must be dropped.
                    ["2026-10-14 09:25", 100, 99, 101, 102, 0],
                    # Malformed row must be dropped.
                    ["bad", None, None, None, None, None],
                ]}

        with patch.object(api, "_require_adapter", return_value=FakeAdapter()):
            response = self.client.get(
                "/v1/market/candles?index=NIFTY&interval=FIVE_MINUTE&days=1",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["source"], "angelone_smartapi_historical_candles")
        self.assertFalse(data["live"])
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["candles"][0]["close"], 102.0)
        self.assertEqual(data["candles"][1]["volume"], 1200.0)

    def test_candle_endpoint_rejects_missing_device_id(self):
        response = self.client.get("/v1/market/candles?index=NIFTY&days=1")
        self.assertEqual(response.status_code, 401)

    def test_candle_endpoint_rejects_unsupported_interval(self):
        response = self.client.get(
            "/v1/market/candles?index=NIFTY&interval=THREE_MINUTE&days=1",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
