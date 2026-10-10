import unittest
from strategies.technical import atr, ema, ema_crossover, rsi, sma
from risk.position_sizing import atr_stop_target, position_size


class ResearchStrategyTests(unittest.TestCase):
    def test_sma_warmup(self):
        self.assertEqual(sma([1, 2, 3, 4], 3), [None, None, 2.0, 3.0])

    def test_ema_seed(self):
        self.assertEqual(ema([1, 2, 3], 3), [None, None, 2.0])

    def test_rsi_uptrend(self):
        self.assertEqual(rsi([1, 2, 3, 4, 5, 6], 3)[3], 100.0)

    def test_atr(self):
        self.assertAlmostEqual(atr([11, 12, 13], [9, 10, 11], [10, 11, 12], 2)[1], 2.0)

    def test_crossover_waits_for_warmup(self):
        self.assertEqual(ema_crossover([1, 2, 3, 4, 5, 6], 2, 3)[:2], ["WAIT", "WAIT"])

    def test_lot_sizing_rounds_down(self):
        self.assertEqual(position_size(100000, 0.01, 100, 95, lot_size=10), 200)

    def test_short_atr_levels(self):
        levels = atr_stop_target(100, 2, "SHORT", 1.5, 2)
        self.assertEqual(levels["stop"], 103.0)
        self.assertEqual(levels["target"], 94.0)


if __name__ == "__main__":
    unittest.main()
