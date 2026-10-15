import unittest
from datetime import datetime
import pandas as pd

from quant.oi_price_action_engine import IST, OIPriceActionEngine, to_signal_data


class OIPriceActionEngineTests(unittest.TestCase):
    def test_outside_window_fails_closed(self):
        now = datetime(2026, 10, 15, 9, 0, tzinfo=IST)
        result = OIPriceActionEngine().generate(pd.DataFrame(), pd.DataFrame(), 25000, now)
        self.assertEqual(result.decision, "WAIT")
        self.assertEqual(result.live_validation["verdict"], "FAIL")

    def test_missing_chain_fails_closed(self):
        now = datetime(2026, 10, 15, 10, 0, tzinfo=IST)
        result = OIPriceActionEngine().generate(pd.DataFrame(), pd.DataFrame(), 25000, now)
        self.assertEqual(result.decision, "WAIT")
        self.assertIn("Option chain missing", result.reasons[0])

    def test_serialization_never_promotes_candidate(self):
        from quant.oi_price_action_engine import QuantSignal
        signal = QuantSignal(candidate_decision="CALL BUY", strike=25000, entry=100,
                             stop_loss=90, target=118, option_side="CE")
        payload = to_signal_data(signal, "NIFTY", "2026-10-15T10:00:00+05:30", True)
        self.assertEqual(payload["decision"], "WAIT")
        self.assertEqual(payload["candidate_decision"], "CALL BUY")
        stale = to_signal_data(signal, data_fresh=False)
        self.assertIsNone(stale["candidate_decision"])
        self.assertIsNone(stale["entry"])

    def test_invalid_configuration_rejected(self):
        with self.assertRaises(ValueError):
            OIPriceActionEngine(atr_period=0)


if __name__ == "__main__":
    unittest.main()
