import unittest
from datetime import datetime, timedelta
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



    def test_depth_pressure_detects_bid_and_ask_imbalance(self):
        engine = OIPriceActionEngine()
        candles = pd.DataFrame([
            {"open": 10, "high": 11, "low": 9, "close": 10},
            {"open": 10, "high": 11, "low": 9, "close": 10},
            {"open": 10, "high": 11, "low": 9, "close": 10},
        ])
        self.assertEqual(engine._pressure(candles, {"bid_qty": 900, "ask_qty": 100}), "BUY_PRESSURE")
        self.assertEqual(engine._pressure(candles, {"bid_qty": 100, "ask_qty": 900}), "SELL_PRESSURE")

    def test_rejection_wicks_and_two_candle_structure(self):
        engine = OIPriceActionEngine()
        bullish = {"open": 10.0, "high": 10.3, "low": 5.0, "close": 10.2}
        bearish = {"open": 10.5, "high": 15.0, "low": 10.3, "close": 10.4}
        self.assertTrue(engine._rejection_wick(bullish, "bull"))
        self.assertTrue(engine._rejection_wick(bearish, "bear"))
        candles = pd.DataFrame([
            {"open": 10, "high": 11, "low": 9, "close": 10.5},
            {"open": 10.5, "high": 12, "low": 10, "close": 11.5},
        ])
        bull, bear, tags = engine._two_candle_structure(candles)
        self.assertTrue(bull)
        self.assertFalse(bear)
        self.assertIn("2-candle HH-HL structure", tags)

    def test_invalid_price_action_configuration_rejected(self):
        with self.assertRaises(ValueError):
            OIPriceActionEngine(hold_bars=0)
        with self.assertRaises(ValueError):
            OIPriceActionEngine(wick_ratio=0)


    def test_candidate_generation_requires_timestamped_option_chain(self):
        now = datetime(2026, 10, 15, 10, 0, tzinfo=IST)
        result = OIPriceActionEngine().generate(
            pd.DataFrame(), pd.DataFrame([{"strike": 25000}]), 25000, now
        )
        self.assertEqual(result.decision, "WAIT")
        self.assertIn("QUOTE_TIMESTAMP_MISSING", result.guards)

    def test_missing_oi_fields_fail_closed_instead_of_zero_filling(self):
        engine = OIPriceActionEngine()
        with self.assertRaisesRegex(ValueError, "Option-chain fields missing"):
            engine._chain(pd.DataFrame([{"strike": 25000, "ce_oi": 100, "pe_oi": 100}]))

    def test_serializer_marks_price_fields_as_underlying_spot(self):
        from quant.oi_price_action_engine import QuantSignal
        payload = to_signal_data(QuantSignal(entry=25000, stop_loss=24900, target=25200))
        self.assertEqual(payload["entry_price_basis"], "UNDERLYING_SPOT")
        self.assertEqual(payload["stop_loss_price_basis"], "UNDERLYING_SPOT")
        self.assertEqual(payload["target_price_basis"], "UNDERLYING_SPOT")


    def test_stale_option_chain_timestamp_fails_closed(self):
        now = datetime(2026, 10, 15, 10, 0, tzinfo=IST)
        chain = pd.DataFrame([{
            "strike": 25000, "ce_oi": 100, "pe_oi": 100,
            "ce_oi_change": 1, "pe_oi_change": 1,
        }])
        result = OIPriceActionEngine().generate(
            pd.DataFrame(), chain, 25000, now,
            option_chain_timestamp=now.replace(minute=58),
        )
        self.assertEqual(result.decision, "WAIT")
        self.assertIn("STALE_OPTION_CHAIN", result.guards)

    def test_stale_completed_candle_fails_closed(self):
        now = datetime(2026, 10, 15, 10, 0, tzinfo=IST)
        candles = pd.DataFrame(
            {"open": [100, 101], "high": [102, 103], "low": [99, 100], "close": [101, 102]},
            index=pd.DatetimeIndex([
                datetime(2026, 10, 15, 9, 20, tzinfo=IST),
                datetime(2026, 10, 15, 9, 25, tzinfo=IST),
            ]),
        )
        chain = pd.DataFrame([{
            "strike": 25000, "ce_oi": 100, "pe_oi": 100,
            "ce_oi_change": 1, "pe_oi_change": 1,
        }])
        result = OIPriceActionEngine().generate(
            candles, chain, 25000, now, option_chain_timestamp=now - timedelta(seconds=5)
        )
        self.assertEqual(result.decision, "WAIT")
        self.assertIn("STALE_CANDLES", result.guards)


if __name__ == "__main__":
    unittest.main()
