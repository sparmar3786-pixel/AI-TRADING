import unittest

from quant.day_hl_liquidity import detect_pdh_pdl_sweeps


class TestDayHLLiquidity(unittest.TestCase):
    def test_pdh_sweep_is_bearish(self):
        result = detect_pdh_pdl_sweeps(
            [{"timestamp": "2026-10-15T09:20:00+05:30", "open": 101, "high": 106, "low": 99, "close": 103}],
            previous_day_high=105,
            previous_day_low=95,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].level_name, "PDH")
        self.assertEqual(result[0].side, "BEARISH")

    def test_pdl_sweep_is_bullish(self):
        result = detect_pdh_pdl_sweeps(
            [{"timestamp": "2026-10-15T09:20:00+05:30", "open": 99, "high": 101, "low": 94, "close": 97}],
            previous_day_high=105,
            previous_day_low=95,
        )
        self.assertEqual([(x.level_name, x.side) for x in result], [("PDL", "BULLISH")])

    def test_touch_without_close_back_is_not_sweep(self):
        result = detect_pdh_pdl_sweeps(
            [{"timestamp": "2026-10-15T09:20:00+05:30", "open": 101, "high": 105, "low": 99, "close": 105}],
            previous_day_high=105,
            previous_day_low=95,
        )
        self.assertEqual(result, [])

    def test_rejects_invalid_levels(self):
        with self.assertRaises(ValueError):
            detect_pdh_pdl_sweeps([], previous_day_high=90, previous_day_low=95)

    def test_rejects_non_chronological_candles(self):
        candles = [
            {"timestamp": "2026-10-15T09:30:00+05:30", "open": 100, "high": 102, "low": 99, "close": 101},
            {"timestamp": "2026-10-15T09:20:00+05:30", "open": 100, "high": 102, "low": 99, "close": 101},
        ]
        with self.assertRaises(ValueError):
            detect_pdh_pdl_sweeps(candles, previous_day_high=105, previous_day_low=95)

    def test_rejects_inconsistent_ohlc(self):
        candles = [{"timestamp": "2026-10-15T09:20:00+05:30", "open": 100, "high": 98, "low": 99, "close": 100}]
        with self.assertRaises(ValueError):
            detect_pdh_pdl_sweeps(candles, previous_day_high=105, previous_day_low=95)


if __name__ == "__main__":
    unittest.main()
