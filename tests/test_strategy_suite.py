import unittest

from strategies.suite import (
    classify_oi_change, evaluate_strategy_suite, liquidity_sweep_signal,
    rate_of_change_signal, stochastic_reversal,
)


def candles(values, volume=100):
    rows = []
    for close in values:
        rows.append({"high": close + 1, "low": close - 1, "close": close, "volume": volume})
    return rows


class StrategySuiteTests(unittest.TestCase):
    def test_empty_and_short_history_fail_closed(self):
        self.assertEqual(evaluate_strategy_suite([])["signal"], "WAIT")
        self.assertEqual(evaluate_strategy_suite(candles([100, 101]))["status"], "insufficient_data")

    def test_bad_candle_fails_closed(self):
        result = evaluate_strategy_suite([{"high": 1, "low": 2, "close": 1}])
        self.assertEqual(result["status"], "invalid_data")
        self.assertEqual(result["signal"], "WAIT")

    def test_oi_classification(self):
        self.assertEqual(classify_oi_change(0.02, 500), "LONG_BUILDUP")
        self.assertEqual(classify_oi_change(-0.02, 500), "SHORT_BUILDUP")
        self.assertEqual(classify_oi_change(0.02, -500), "SHORT_COVERING")
        self.assertEqual(classify_oi_change(-0.02, -500), "LONG_UNWINDING")
        self.assertEqual(classify_oi_change(0, 500), "UNKNOWN")

    def test_roc_momentum(self):
        self.assertEqual(rate_of_change_signal([100 + i for i in range(12)]), "LONG")
        self.assertEqual(rate_of_change_signal([100 - i for i in range(12)]), "SHORT")

    def test_liquidity_sweep_uses_prior_levels(self):
        highs = [101.0 + (i % 3) for i in range(21)]
        lows = [99.0 - (i % 3) for i in range(21)]
        closes = [100.0] * 20 + [100.0]
        highs[-1] = max(highs[:-1]) + 1.0
        self.assertEqual(liquidity_sweep_signal(highs, lows, closes, lookback=20), "SHORT")

    def test_stochastic_warmup_waits(self):
        self.assertEqual(stochastic_reversal([2, 3], [1, 2], [1.5, 2.5], period=14), "WAIT")

    def test_full_suite_returns_named_strategies_and_levels(self):
        result = evaluate_strategy_suite(candles([100 + i * 0.8 for i in range(35)]), min_consensus=2)
        self.assertEqual(result["status"], "ok")
        self.assertIn("ema_9_21", result["strategies"])
        self.assertIn("donchian_breakout", result["strategies"])
        self.assertIn("support", result["support_resistance"])
        self.assertEqual(result["execution"], "disabled")

    def test_no_trade_without_consensus(self):
        result = evaluate_strategy_suite(candles([100, 101, 100, 101, 100, 101]), min_consensus=3)
        self.assertEqual(result["signal"], "WAIT")
        self.assertIsNone(result["risk_levels"])


if __name__ == "__main__":
    unittest.main()
