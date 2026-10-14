import unittest
from datetime import datetime, timedelta, timezone

from quant_engine import evaluate_futures_signal


class FuturesOrderFlowSemanticsTests(unittest.TestCase):
    def test_mcx_bid_ask_depth_is_not_labeled_trade_volume(self):
        now = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
        snapshot = {
            "observed_at": now.isoformat(),
            "underlying_ltp": 100.0,
            "sentiment_score": 0.55,
            "timeframe_closes": {
                "5m": [90, 92, 94, 97, 100],
                "15m": [88, 90, 93, 96, 100],
                "1h": [85, 89, 92, 96, 100],
            },
            "indicators": {
                "ema_fast_8": 101.0, "ema_slow_21": 99.0,
                "rsi_14": 60.0, "macd_histogram": 1.5,
                "underlying_atr_14": 2.0, "vwap": 95.0,
            },
            "order_flow": {
                "bid": 99.9, "ask": 100.1, "ltp": 100.0,
                "bid_depth": 600, "ask_depth": 400,
                "semantics": "bid_ask_depth_not_classified_trade_volume",
            },
            "contract": {
                "symbol": "GOLD26OCTFUT",
                "expiry": (now.date() + timedelta(days=10)).isoformat(),
                "volume": 12000, "oi": 200000, "lot_size": 10,
            },
        }

        result = evaluate_futures_signal(snapshot, now=now)
        layer = result["layers"]["order_flow"]

        self.assertTrue(layer["pass"])
        self.assertEqual(layer["measure"], "BOOK_DEPTH_IMBALANCE")
        self.assertEqual(layer["semantics"], "bid_ask_depth_not_classified_trade_volume")


if __name__ == "__main__":
    unittest.main()
