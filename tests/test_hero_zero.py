"""Regression tests for the fail-closed Hero Zero expiry candidate engine."""
import unittest
from datetime import datetime, timedelta, date

import pandas as pd

from quant.hero_zero import HeroZeroEngine, hero_zero_to_signal_data, IST


NOW = datetime(2026, 10, 15, 13, 45, tzinfo=IST)


def candles(*, breakout=True, volume=True, stale=False):
    start = datetime(2026, 10, 15, 9, 15, tzinfo=IST)
    times = [start + timedelta(minutes=5 * i) for i in range(55)]
    closes = [22500.0 + (i % 3) for i in range(55)]
    if breakout:
        closes[51:54] = [22510.0, 22520.0, 22530.0]
    highs = [c + 2 for c in closes]
    lows = [c - 2 for c in closes]
    opens = [c - 0.5 for c in closes]
    vols = [100.0] * 55
    vols[53] = 500.0
    if stale:
        times = [t - timedelta(minutes=30) for t in times]
    frame = {"open": opens, "high": highs, "low": lows, "close": closes}
    if volume:
        frame["volume"] = vols
    return pd.DataFrame(frame, index=pd.DatetimeIndex(times))


def chain():
    # spot 22525 rounds to ATM 22550; +1 CE strike is 22600.
    return pd.DataFrame([{"strike": 22600, "ce_ltp": 12.0, "pe_ltp": 14.0,
                          "ce_bid": 11.8, "ce_ask": 12.2}])


class HeroZeroTests(unittest.TestCase):
    def setUp(self):
        self.engine = HeroZeroEngine(hold_bars=2, require_volume=True)
        self.kw = dict(
            intraday_df=candles(), current_spot=22525, is_expiry_day=True,
            option_chain=chain(), current_time=NOW, strike_step=50,
            expiry_date=date(2026, 10, 15),
            option_chain_timestamp=NOW - timedelta(seconds=3),
        )

    def test_confirmed_setup_is_candidate_not_actionable(self):
        sig = self.engine.generate(**self.kw)
        self.assertEqual(sig.candidate_decision, "CALL BUY")
        self.assertEqual(sig.decision, "CALL BUY")
        self.assertEqual(sig.strike, 22600)
        self.assertEqual(sig.option_side, "CE")
        self.assertEqual(sig.entry, 12.0)
        self.assertEqual(sig.stop_loss, 6.0)
        self.assertEqual(sig.target, 36.0)
        payload = hero_zero_to_signal_data(sig, index="NIFTY", timestamp=NOW.isoformat())
        self.assertEqual(payload["decision"], "WAIT")
        self.assertEqual(payload["candidate_decision"], "CALL BUY")
        self.assertEqual(payload["confidence"], 0.0)

    def test_expiry_must_be_verified(self):
        kwargs = dict(self.kw)
        kwargs["expiry_date"] = None
        sig = self.engine.generate(**kwargs)
        self.assertEqual(sig.decision, "WAIT")
        self.assertIn("EXPIRY_NOT_VERIFIED", sig.guards)

    def test_stale_quote_fails_closed(self):
        kwargs = dict(self.kw)
        kwargs["option_chain_timestamp"] = NOW - timedelta(minutes=2)
        sig = self.engine.generate(**kwargs)
        self.assertEqual(sig.decision, "WAIT")
        self.assertIn("STALE_OPTION_CHAIN", sig.guards)

    def test_missing_quote_timestamp_fails_closed(self):
        kwargs = dict(self.kw)
        kwargs["option_chain_timestamp"] = None
        sig = self.engine.generate(**kwargs)
        self.assertEqual(sig.decision, "WAIT")
        self.assertIn("QUOTE_TIMESTAMP_MISSING", sig.guards)

    def test_missing_volume_fails_closed(self):
        kwargs = dict(self.kw)
        kwargs["intraday_df"] = candles(volume=False)
        sig = self.engine.generate(**kwargs)
        self.assertEqual(sig.decision, "WAIT")
        self.assertIn("INVALID_INPUT", sig.guards)

    def test_no_breakout_returns_wait(self):
        kwargs = dict(self.kw)
        kwargs["intraday_df"] = candles(breakout=False)
        sig = self.engine.generate(**kwargs)
        self.assertEqual(sig.decision, "WAIT")
        self.assertIsNone(sig.entry)

    def test_stale_data_mapper_removes_candidate_prices(self):
        sig = self.engine.generate(**self.kw)
        payload = hero_zero_to_signal_data(sig, index="NIFTY", data_fresh=False)
        self.assertEqual(payload["decision"], "WAIT")
        self.assertIsNone(payload["candidate_decision"])
        self.assertIsNone(payload["entry"])
        self.assertIn("STALE_DATA", payload["guards"])

    def test_wide_spread_fails_closed(self):
        kwargs = dict(self.kw)
        kwargs["option_chain"] = pd.DataFrame([{
            "strike": 22600, "ce_ltp": 12.0, "pe_ltp": 14.0,
            "ce_bid": 10.0, "ce_ask": 13.0,
        }])
        sig = self.engine.generate(**kwargs)
        self.assertEqual(sig.decision, "WAIT")
        self.assertIn("WIDE_SPREAD", sig.guards)

    def test_invalid_configuration_rejected(self):
        with self.assertRaises(ValueError):
            HeroZeroEngine(hold_bars=0)
        with self.assertRaises(ValueError):
            HeroZeroEngine(min_premium=0, max_premium=10)


if __name__ == "__main__":
    unittest.main()
