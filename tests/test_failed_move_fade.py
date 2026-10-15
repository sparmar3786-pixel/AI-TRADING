"""Regression tests for the isolated failed-move continuation engine."""
import unittest
from datetime import datetime, timedelta

import pandas as pd

from quant.failed_move_fade import FailedMoveFadeEngine, failed_move_to_signal_data, IST


def sample_daily():
    return pd.DataFrame(
        {"high": [100.0], "low": [90.0], "close": [95.0]},
        index=pd.DatetimeIndex([datetime(2026, 10, 14, 15, 30, tzinfo=IST)]),
    )


def sample_intraday(*, breakout=True, volume=True):
    start = datetime(2026, 10, 15, 9, 15, tzinfo=IST)
    times = [start + timedelta(minutes=5 * i) for i in range(28)]
    closes = [95.0 + (0.05 * (i % 3)) for i in range(28)]
    if breakout:
        # Last three completed candles close above PDH; final row is the forming bar.
        closes[24:27] = [101.0, 102.0, 103.0]
        closes[27] = 103.2
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    frame = {"high": highs, "low": lows, "close": closes}
    if volume:
        frame["volume"] = [100.0] * 24 + [500.0, 500.0, 500.0, 500.0]
    return pd.DataFrame(frame, index=pd.DatetimeIndex(times))


class FailedMoveFadeTests(unittest.TestCase):
    def setUp(self):
        self.engine = FailedMoveFadeEngine(
            hold_bars=3,
            atr_period=14,
            use_volume_filter=True,
            volume_mult=1.3,
            drop_forming_candle=True,
        )
        self.now = datetime(2026, 10, 15, 11, 30, tzinfo=IST)

    def test_pdh_acceptance_emits_candidate_not_actionable_decision(self):
        signal = self.engine.generate(sample_daily(), sample_intraday(), 103.2, self.now)
        self.assertEqual(signal.decision, "CALL BUY")
        self.assertEqual(signal.candidate_decision, "CALL BUY")
        self.assertEqual(signal.option_side, "CE")
        self.assertIsNotNone(signal.stop_loss)
        self.assertIsNotNone(signal.target)
        mapped = failed_move_to_signal_data(
            signal, index="NIFTY", timestamp=self.now.isoformat(), data_fresh=True
        )
        self.assertEqual(mapped["decision"], "WAIT")
        self.assertEqual(mapped["candidate_decision"], "CALL BUY")
        self.assertEqual(mapped["live_validation"]["verdict"], "PENDING")
        self.assertEqual(mapped["decision"], "WAIT")
        self.assertEqual(mapped["entry_price_basis"], "UNDERLYING_SPOT")
        self.assertEqual(mapped["signal_stability"]["remaining_seconds"], 600)

    def test_stale_data_clears_candidate_and_prices(self):
        signal = self.engine.generate(sample_daily(), sample_intraday(), 103.2, self.now)
        mapped = failed_move_to_signal_data(
            signal, index="NIFTY", timestamp=self.now.isoformat(), data_fresh=False
        )
        self.assertEqual(mapped["decision"], "WAIT")
        self.assertIsNone(mapped["candidate_decision"])
        self.assertIsNone(mapped["entry"])
        self.assertIn("STALE_DATA", mapped["guards"])

    def test_missing_volume_fails_closed(self):
        signal = self.engine.generate(
            sample_daily(), sample_intraday(volume=False), 103.2, self.now
        )
        self.assertEqual(signal.decision, "WAIT")
        self.assertIn("MISSING_VOLUME", signal.guards)

    def test_no_acceptance_returns_wait(self):
        signal = self.engine.generate(
            sample_daily(), sample_intraday(breakout=False), 95.0, self.now
        )
        self.assertEqual(signal.decision, "WAIT")
        self.assertIsNone(signal.entry)

    def test_outside_window_returns_wait(self):
        signal = self.engine.generate(
            sample_daily(), sample_intraday(), 103.2,
            datetime(2026, 10, 15, 14, 30, tzinfo=IST),
        )
        self.assertEqual(signal.decision, "WAIT")
        self.assertIn("Outside failed-move window", signal.reasons[0])


if __name__ == "__main__":
    unittest.main()
