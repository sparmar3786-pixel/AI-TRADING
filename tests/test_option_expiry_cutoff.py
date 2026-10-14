import unittest
from datetime import datetime, timezone

from quant_engine import evaluate_five_layer_signal


class OptionExpiryCutoffTests(unittest.TestCase):
    def test_expiry_day_option_is_rejected_after_nse_market_close(self):
        # 15:31 IST on the expiry date. Date-only expiry values are exchange
        # calendar dates and must not be treated as valid until 23:59 UTC.
        now = datetime(2026, 10, 29, 10, 1, tzinfo=timezone.utc)
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
                "buy_volume": 600, "sell_volume": 400,
            },
            "option_chain": [{
                "option_type": "CALL", "strike": 22000, "expiry": "2026-10-29",
                "bid": 99.9, "ask": 100.1, "ltp": 100.0, "volume": 12000,
                "oi": 200000, "delta": 0.52, "option_atr": 2.0,
                "timestamp": now.isoformat(),
            }],
        }

        result = evaluate_five_layer_signal(snapshot, now=now)

        self.assertEqual(result["decision"], "WAIT")
        self.assertFalse(result["layers"]["option_selection"]["pass"])
        self.assertIsNone(result["entry"])


if __name__ == "__main__":
    unittest.main()
