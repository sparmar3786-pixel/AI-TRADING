import unittest
from datetime import datetime, timezone

from quant_engine import evaluate_five_layer_signal


class OrderFlowSemanticsTests(unittest.TestCase):
    def test_book_depth_is_labeled_as_depth_not_trade_volume(self):
        now = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
        snapshot = {
            "observed_at": now.isoformat(),
            "underlying_ltp": 22010,
            "sentiment_score": 0.55,
            "timeframe_closes": {
                "5m": [21970, 21980, 21995, 22000, 22010],
                "15m": [21930, 21945, 21960, 21980, 22000],
                "1h": [21850, 21880, 21900, 21950, 22010],
            },
            "order_flow": {
                "bid": 99.9, "ask": 100.1, "ltp": 100.0,
                "bid_depth": 600, "ask_depth": 400,
                "semantics": "bid_ask_depth_not_classified_trade_volume",
            },
            "option_chain": [{
                "option_type": "CALL", "strike": 22000, "expiry": "2026-10-29",
                "bid": 99.9, "ask": 100.1, "ltp": 100.0, "volume": 12000,
                "oi": 200000, "delta": 0.52, "option_atr": 2.0,
                "timestamp": now.isoformat(),
            }],
        }

        result = evaluate_five_layer_signal(snapshot, now=now)
        layer = result["layers"]["order_flow"]

        self.assertTrue(layer["pass"])
        self.assertAlmostEqual(layer["imbalance"], 0.2)
        self.assertEqual(layer["measure"], "BOOK_DEPTH_IMBALANCE")
        self.assertEqual(layer["semantics"], "bid_ask_depth_not_classified_trade_volume")


if __name__ == "__main__":
    unittest.main()
