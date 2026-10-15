import unittest
import numpy as np
import pandas as pd

from quant.ema_quant_engine import EMAQuantEngine, QuantSignal, to_signal_data


class EMAQuantEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = EMAQuantEngine(skip_first_minutes=0, use_volume_filter=False)

    def candles(self, n=60):
        idx = pd.date_range("2026-10-15 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
        close = np.linspace(100, 110, n)
        return pd.DataFrame({
            "open": close - 0.1, "high": close + 0.5,
            "low": close - 0.5, "close": close, "volume": np.full(n, 1000),
        }, index=idx)

    def test_empty_data_fails_closed(self):
        signal = self.engine.generate(pd.DataFrame(), 25000)
        self.assertEqual(signal.decision, "WAIT")
        self.assertIsNone(signal.entry)
        self.assertIsNone(signal.stop_loss)
        self.assertIsNone(signal.target)

    def test_requires_datetime_index(self):
        df = self.candles()
        df.index = range(len(df))
        signal = self.engine.generate(df, 25000)
        self.assertEqual(signal.decision, "WAIT")
        self.assertIn("DatetimeIndex", signal.reasons[0])

    def test_missing_volume_fails_closed_when_filter_enabled(self):
        df = self.candles().drop(columns=["volume"])
        signal = EMAQuantEngine(skip_first_minutes=0, use_volume_filter=True).generate(df, 25000)
        self.assertEqual(signal.decision, "WAIT")
        self.assertIn("volume data is missing", signal.reasons[0])

    def test_half_up_strike_rounding(self):
        self.assertEqual(EMAQuantEngine._atm_strike(25025, 50), 25050.0)
        self.assertEqual(EMAQuantEngine._atm_strike(25024.99, 50), 25000.0)

    def test_invalid_spot_fails_closed(self):
        signal = self.engine.generate(self.candles(), float("nan"))
        self.assertEqual(signal.decision, "WAIT")
        self.assertIsNone(signal.strike)

    def test_signal_mapping_never_promotes_candidate_to_actionable(self):
        signal = QuantSignal(decision="CALL BUY", candidate_decision="CALL BUY",
                             entry=100, stop_loss=98, target=104, strike=100, option_side="CE")
        payload = to_signal_data(signal, index="NIFTY")
        self.assertEqual(payload["decision"], "WAIT")
        self.assertEqual(payload["candidate_decision"], "CALL BUY")
        self.assertEqual(payload["engine_source"], "EMA")

    def test_drops_newest_forming_bar(self):
        df = self.candles(10)
        signal = self.engine.generate(df, 25000)
        self.assertEqual(signal.decision, "WAIT")
        self.assertIn("Insufficient completed candles", signal.reasons[0])


if __name__ == "__main__":
    unittest.main()
