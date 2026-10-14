import unittest

from strategies.smc import analyze_smc


def bars(closes):
    result = []
    for close in closes:
        result.append({
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        })
    return result


class SMCEngineTests(unittest.TestCase):
    def test_missing_timeframe_candles_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "at least 5"):
            analyze_smc(
                instrument="NIFTY",
                htf_candles=bars([100, 101, 102, 103, 104]),
                mtf_candles=bars([100, 101, 102, 103, 104]),
                ltf_candles=[],
            )

    def test_response_is_signal_only_and_has_three_timeframe_diagnostics(self):
        candles_up = bars([100, 101, 102, 103, 104, 105, 106])
        result = analyze_smc(
            instrument="nifty",
            htf_candles=candles_up,
            mtf_candles=candles_up,
            ltf_candles=candles_up,
            strategy_format="Guardeer",
        )
        self.assertEqual(result["instrument"], "NIFTY")
        self.assertIn(result["signal"], {"LONG", "SHORT", "NO TRADE"})
        self.assertIn("htf", result["timeframes"])
        self.assertIn("mtf", result["timeframes"])
        self.assertIn("ltf", result["timeframes"])
        self.assertFalse(result["execution_allowed"])
        self.assertTrue(result["signal_only"])

    def test_invalid_strategy_format_is_rejected(self):
        candles_up = bars([100, 101, 102, 103, 104])
        with self.assertRaisesRegex(ValueError, "strategy_format"):
            analyze_smc(
                instrument="NIFTY",
                htf_candles=candles_up,
                mtf_candles=candles_up,
                ltf_candles=candles_up,
                strategy_format="unknown",
            )


if __name__ == "__main__":
    unittest.main()
