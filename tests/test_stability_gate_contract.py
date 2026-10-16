"""Regression tests for P3 signal stability and quote freshness contract."""
import unittest
from datetime import datetime, timedelta, timezone

from quant_engine import evaluate_five_layer_signal


class StabilityGateContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
        self.snapshot = {
            "observed_at": self.now.isoformat(),
            "underlying_ltp": 22010,
            "sentiment_score": 0.55,
            "timeframe_closes": {
                "5m": [21970, 21980, 21995, 22000, 22010],
                "15m": [21930, 21945, 21960, 21980, 22000],
                "1h": [21850, 21880, 21900, 21950, 22010],
            },
            "order_flow": {
                "bid": 99.9, "ask": 100.1, "ltp": 100.0,
                "buy_volume": 600, "sell_volume": 400,
            },
            "option_chain": [{
                "option_type": "CALL", "strike": 22000, "expiry": "2026-10-29",
                "bid": 99.9, "ask": 100.1, "ltp": 100.0, "volume": 12000,
                "oi": 200000, "delta": 0.52, "option_atr": 2.0,
                "timestamp": self.now.isoformat(),
            }],
        }

    def _refresh(self, snapshot, elapsed, state):
        now = self.now + timedelta(seconds=elapsed)
        snap = dict(snapshot)
        snap["observed_at"] = now.isoformat()
        snap["option_chain"] = [
            dict(row, timestamp=now.isoformat())
            for row in snapshot["option_chain"]
        ]
        return evaluate_five_layer_signal(snap, now=now, confirmation_state=state)

    def test_option_chain_timestamp_is_mandatory_and_not_borrowed_from_spot(self):
        self.snapshot["option_chain"][0].pop("timestamp")
        result = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertEqual(result["decision"], "WAIT")
        self.assertFalse(result["layers"]["option_selection"]["pass"])
        self.assertIsNone(result["strike"])
        self.assertIsNone(result["entry"])
        self.assertIsNone(result["stop_loss"])
        self.assertIsNone(result["target"])

    def test_stability_contract_exposes_600_seconds_and_refresh_gap(self):
        result = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertEqual(result["signal_stability"]["required_seconds"], 600)
        self.assertEqual(result["signal_stability"]["required_minutes"], 10)
        self.assertEqual(result["signal_stability"]["max_refresh_gap_seconds"], 60)
        self.assertEqual(result["signal_stability"]["state"], "CONFIRMING")
        self.assertFalse(result["order_placement_enabled"])

    def test_strike_change_restarts_the_full_confirmation_timer(self):
        first = evaluate_five_layer_signal(self.snapshot, now=self.now)
        changed = dict(self.snapshot)
        changed["option_chain"] = [dict(self.snapshot["option_chain"][0], strike=22050)]
        result = self._refresh(changed, 300, first["confirmation_state"])
        self.assertEqual(result["decision"], "WAIT")
        self.assertEqual(result["signal_stability"]["state"], "CONFIRMING")
        self.assertEqual(
            result["signal_stability"]["since_utc"],
            (self.now + timedelta(seconds=300)).isoformat(),
        )
        self.assertIn("restarting 10-minute confirmation", " ".join(result["reasons"]))

    def test_validation_failure_clears_levels_and_resets_confirmation_state(self):
        first = evaluate_five_layer_signal(self.snapshot, now=self.now)
        bad = dict(self.snapshot)
        bad["option_chain"] = [dict(self.snapshot["option_chain"][0], bid=0)]
        result = self._refresh(bad, 30, first["confirmation_state"])
        self.assertEqual(result["decision"], "WAIT")
        self.assertEqual(result["signal_stability"]["state"], "BLOCKED")
        self.assertEqual(result["confirmation_state"], {})
        self.assertIsNone(result["strike"])
        self.assertIsNone(result["entry"])
        self.assertIsNone(result["stop_loss"])
        self.assertIsNone(result["target"])
        self.assertFalse(result["order_placement_enabled"])

    def test_gap_over_60_seconds_restarts_timer_instead_of_confirming(self):
        first = evaluate_five_layer_signal(self.snapshot, now=self.now)
        result = self._refresh(self.snapshot, 61, first["confirmation_state"])
        self.assertEqual(result["decision"], "WAIT")
        self.assertEqual(result["signal_stability"]["state"], "CONFIRMING")
        self.assertEqual(
            result["signal_stability"]["since_utc"],
            (self.now + timedelta(seconds=61)).isoformat(),
        )


if __name__ == "__main__":
    unittest.main()
