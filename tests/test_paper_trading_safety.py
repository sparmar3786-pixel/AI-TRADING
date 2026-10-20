"""Regression tests for fail-closed paper-trading helpers; no broker calls/orders."""
import unittest
from datetime import datetime, timedelta, timezone

from quant.paper_trading_safety import (
    MarketDataError,
    floor_to_lot,
    normalize_smartapi_candles,
    require_fresh_quote,
    target_exit_quantity,
    unrealized_pnl,
)


class PaperTradingSafetyTests(unittest.TestCase):
    def test_normalizes_smartapi_list_payload_and_string_timestamps(self):
        result = normalize_smartapi_candles({
            "status": True,
            "data": [
                ["2026-10-20T09:15:00+05:30", "100", "103", "99", "102", "500"],
                ["2026-10-20T09:20:00+05:30", 102, 104, 101, 103, 600],
            ],
        })
        self.assertEqual(len(result), 2)
        self.assertEqual(float(result.iloc[-1]["close"]), 103.0)
        self.assertIsNotNone(result.index.tz)

    def test_normalizes_nested_candles_payload_and_sorts(self):
        result = normalize_smartapi_candles({
            "data": {"candles": [
                [1792488000, 102, 103, 101, 102, 100],
                [1792487700, 100, 102, 99, 101, 90],
            ]}
        })
        self.assertEqual(len(result), 2)
        self.assertLess(result.index[0], result.index[1])

    def test_bad_or_empty_candles_fail_closed(self):
        with self.assertRaises(MarketDataError):
            normalize_smartapi_candles({"data": []})
        with self.assertRaises(MarketDataError):
            normalize_smartapi_candles({"data": [[
                "2026-10-20T09:15:00Z", 100, 98, 99, 101, 10
            ]]})

    def test_quantity_is_lot_aligned(self):
        self.assertEqual(floor_to_lot(99, 25), 75)
        self.assertEqual(floor_to_lot(24, 25), 0)
        with self.assertRaises(ValueError):
            floor_to_lot(20, 0)

    def test_partial_exit_tranches_use_original_quantity_and_remaining_cap(self):
        self.assertEqual(target_exit_quantity(100, 0, 30, 25), 25)
        self.assertEqual(target_exit_quantity(100, 25, 40, 25), 25)
        self.assertEqual(target_exit_quantity(100, 50, 60, 25), 50)
        self.assertEqual(target_exit_quantity(100, 75, 40, 25), 25)

    def test_pnl_uses_traded_instrument_mark_and_side(self):
        self.assertEqual(unrealized_pnl(100, 110, 25, "BUY"), 250)
        self.assertEqual(unrealized_pnl(100, 90, 25, "SELL"), 250)
        with self.assertRaises(ValueError):
            unrealized_pnl(100, 110, 25, "CALL")

    def test_quote_freshness_rejects_stale_and_future_data(self):
        now = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
        require_fresh_quote(now - timedelta(seconds=2), now, 5)
        with self.assertRaises(MarketDataError):
            require_fresh_quote(now - timedelta(seconds=10), now, 5)
        with self.assertRaises(MarketDataError):
            require_fresh_quote(now + timedelta(seconds=1), now, 5)


if __name__ == "__main__":
    unittest.main()
