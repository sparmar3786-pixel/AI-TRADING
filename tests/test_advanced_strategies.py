import unittest
from strategies.advanced import bollinger_bands, donchian_breakout, macd, vwap
from backtesting.engine import run_backtest
from risk.controls import validate_proposed_order


class AdvancedStrategyTests(unittest.TestCase):
    def test_bollinger_warmup(self):
        bands = bollinger_bands([1, 2, 3], period=3)
        self.assertIsNone(bands["middle"][0])
        self.assertAlmostEqual(bands["middle"][2], 2.0)

    def test_donchian_excludes_current_bar(self):
        signals = donchian_breakout([10, 11, 12, 15], [10, 11, 12, 15], [9, 10, 11, 14], 3)
        self.assertEqual(signals[:3], ["WAIT", "WAIT", "WAIT"])
        self.assertEqual(signals[3], "LONG")

    def test_macd_shapes(self):
        result = macd(list(range(1, 50)), 3, 6, 2)
        self.assertEqual(len(result["line"]), 49)
        self.assertIsNone(result["histogram"][0])

    def test_vwap_zero_volume(self):
        self.assertEqual(vwap([2], [1], [1.5], [0]), [None])

    def test_backtest_delays_signal_and_charges_cost(self):
        result = run_backtest([100, 110, 110], ["LONG", "LONG", "FLAT"], 0, 0)
        self.assertAlmostEqual(result["total_return"], 0.1)
        self.assertEqual(result["return_observations"], 2)

    def test_backtest_rejects_bad_prices(self):
        with self.assertRaises(ValueError):
            run_backtest([100, 0], ["LONG", "FLAT"])

    def test_risk_gate_stale_data_fails(self):
        result = validate_proposed_order(equity=100000, entry=100, stop=99, quantity=10,
            open_positions=0, daily_pnl_fraction=0, data_age_seconds=60)
        self.assertFalse(result["approved"])
        self.assertIn("MARKET_DATA_STALE_OR_INVALID", result["reasons"])


if __name__ == "__main__":
    unittest.main()
