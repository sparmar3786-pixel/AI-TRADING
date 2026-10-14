import unittest
from datetime import datetime, timezone

from quant_engine import evaluate_futures_signal


class FuturesExpiryLocalDateTests(unittest.TestCase):
    def test_date_only_futures_expiry_is_invalid_after_local_calendar_day(self):
        # 06:00 IST on the day after the contract expiry date.
        now = datetime(2026, 10, 15, 0, 30, tzinfo=timezone.utc)
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
                "buy_volume": 600, "sell_volume": 400,
            },
            "contract": {
                "symbol": "GOLD14OCTFUT",
                "expiry": "2026-10-14",
                "volume": 12000, "oi": 200000, "lot_size": 10,
            },
        }

        result = evaluate_futures_signal(snapshot, now=now)

        self.assertEqual(result["decision"], "WAIT")
        self.assertFalse(result["layers"]["contract_selection"]["pass"])
        self.assertFalse(result["order_placement_enabled"])


if __name__ == "__main__":
    unittest.main()
