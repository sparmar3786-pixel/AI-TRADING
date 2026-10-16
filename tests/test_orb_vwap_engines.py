"""Regression tests for ORB and VWAP candidate engines; no live data or orders."""
import unittest
from datetime import datetime, timedelta

import pandas as pd

from quant.orb_engine import IST, OpeningRangeBreakoutEngine
from quant.vwap_strategy import VWAPStrategyEngine


def candles(closes, volumes=None, start_time=(9, 15)):
    start = datetime(2026, 10, 15, start_time[0], start_time[1], tzinfo=IST)
    times = [start + timedelta(minutes=5 * i) for i in range(len(closes))]
    opens = [closes[0]] + closes[:-1]
    frame = {
        "open": opens,
        "high": [max(o, c) + 0.5 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 0.5 for o, c in zip(opens, closes)],
        "close": closes,
        "volume": volumes or [100.0] * len(closes),
    }
    return pd.DataFrame(frame, index=pd.DatetimeIndex(times))


class ORBEngineTests(unittest.TestCase):
    def test_bullish_breakout_candidate_has_risk_levels_but_is_not_validated(self):
        frame = candles([100, 101, 100.5, 100.5, 101, 100.8, 103, 104], [100, 100, 100, 110, 120, 130, 180, 200])
        result = OpeningRangeBreakoutEngine(use_volume_filter=True).generate(
            frame, 25012, datetime(2026, 10, 15, 9, 51, tzinfo=IST))
        self.assertEqual(result.candidate_decision, "CALL BUY")
        self.assertEqual(result.option_side, "CE")
        self.assertLess(result.stop_loss, result.entry)
        self.assertGreater(result.target, result.entry)
        self.assertEqual(result.live_validation["verdict"], "PENDING")

    def test_missing_volume_fails_closed(self):
        frame = candles([100, 101, 100.5, 102, 103, 104, 105]).drop(columns="volume")
        result = OpeningRangeBreakoutEngine().generate(frame, 25000, datetime(2026, 10, 15, 9, 51, tzinfo=IST))
        self.assertEqual(result.decision, "WAIT")

    def test_outside_window_waits(self):
        result = OpeningRangeBreakoutEngine().generate(candles([100, 101, 100.5, 102]), 25000,
            datetime(2026, 10, 15, 15, 0, tzinfo=IST))
        self.assertEqual(result.decision, "WAIT")


class VWAPEngineTests(unittest.TestCase):
    def test_vwap_cross_candidate_has_risk_levels(self):
        closes = [100, 99.8, 99.5, 99.4, 99.3, 99.2] + [99.2] * 11 + [100.5, 101.5]
        volumes = [100, 100, 110, 120, 130, 150] + [100] * 11 + [250, 300]
        frame = candles(closes, volumes)
        result = VWAPStrategyEngine(use_volume_filter=True, volume_mult=1.0).generate(
            frame, 25012, datetime(2026, 10, 15, 10, 46, tzinfo=IST))
        self.assertEqual(result.candidate_decision, "CALL BUY")
        self.assertIsNotNone(result.vwap)
        self.assertLess(result.stop_loss, result.entry)
        self.assertGreater(result.target, result.entry)
        self.assertEqual(result.live_validation["verdict"], "PENDING")

    def test_missing_volume_fails_closed(self):
        closes = [100, 99.8, 99.5, 99.4, 99.3, 99.2] + [99.2] * 11 + [100.5, 101.5]
        frame = candles(closes).drop(columns="volume")
        result = VWAPStrategyEngine().generate(frame, 25012, datetime(2026, 10, 15, 10, 46, tzinfo=IST))
        self.assertEqual(result.decision, "WAIT")

    def test_outside_window_waits(self):
        result = VWAPStrategyEngine().generate(candles([100, 99.8, 99.5, 99.4, 99.3, 99.6, 100.5, 101.5]),
            25012, datetime(2026, 10, 15, 15, 0, tzinfo=IST))
        self.assertEqual(result.decision, "WAIT")


if __name__ == "__main__":
    unittest.main()
