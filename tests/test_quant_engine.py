import unittest
from datetime import datetime, timedelta, timezone

from quant_engine import evaluate_five_layer_signal, evaluate_futures_signal


class FiveLayerEngineTests(unittest.TestCase):
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

    def test_missing_or_stale_market_data_fails_closed(self):
        result = evaluate_five_layer_signal(self.snapshot, now=self.now + timedelta(seconds=16))
        self.assertEqual(result["decision"], "WAIT")
        self.assertFalse(result["layers"]["data_quality"]["pass"])
        self.assertIsNone(result["entry"])

    def test_epoch_seconds_and_milliseconds_are_normalized(self):
        for key, stamp in (
            ("observed_at", self.now.timestamp()),
            ("timestamp", self.now.timestamp() * 1000),
            ("source_timestamp", self.now.isoformat()),
        ):
            snapshot = dict(self.snapshot)
            snapshot.pop("observed_at", None)
            snapshot[key] = stamp
            result = evaluate_five_layer_signal(snapshot, now=self.now)
            self.assertTrue(result["layers"]["data_quality"]["pass"], result["layers"]["data_quality"])
            self.assertEqual(result["layers"]["data_quality"]["reason_code"], "OK")

    def test_data_quality_exposes_specific_reason_for_missing_timestamp(self):
        snapshot = dict(self.snapshot)
        snapshot.pop("observed_at")
        result = evaluate_five_layer_signal(snapshot, now=self.now)
        self.assertFalse(result["layers"]["data_quality"]["pass"])
        self.assertEqual(result["layers"]["data_quality"]["reason_code"], "MISSING_OR_INVALID_TIMESTAMP")
        self.assertIn("timestamp", result["layers"]["data_quality"]["reason"].lower())

    def test_small_future_clock_skew_is_tolerated_but_large_skew_is_rejected(self):
        snapshot = dict(self.snapshot, observed_at=(self.now + timedelta(seconds=1)).isoformat())
        tolerated = evaluate_five_layer_signal(snapshot, now=self.now)
        self.assertTrue(tolerated["layers"]["data_quality"]["pass"])
        snapshot["observed_at"] = (self.now + timedelta(seconds=5)).isoformat()
        rejected = evaluate_five_layer_signal(snapshot, now=self.now)
        self.assertFalse(rejected["layers"]["data_quality"]["pass"])
        self.assertEqual(rejected["layers"]["data_quality"]["reason_code"], "FUTURE_TIMESTAMP")

    def test_first_valid_candidate_waits_for_ten_minutes(self):
        result = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertEqual(result["decision"], "WAIT")
        self.assertEqual(result["candidate_decision"], "CALL BUY")
        self.assertEqual(result["layers"]["confirmation"]["state"], "CONFIRMING")
        self.assertEqual(result["entry"], 100.1)
        self.assertEqual(result["stop_loss"], 97.1)
        self.assertEqual(result["target"], 106.1)
        self.assertTrue(result["signal_only"])

    def test_stable_candidate_can_confirm_after_ten_minutes(self):
        result = evaluate_five_layer_signal(self.snapshot, now=self.now)
        state = result["confirmation_state"]
        # Refresh every 30 seconds so the data-continuity guard remains satisfied.
        for elapsed in range(30, 631, 30):
            next_now = self.now + timedelta(seconds=elapsed)
            next_snapshot = dict(self.snapshot)
            next_snapshot["observed_at"] = next_now.isoformat()
            next_snapshot["option_chain"] = [
                dict(self.snapshot["option_chain"][0], timestamp=next_now.isoformat())
            ]
            result = evaluate_five_layer_signal(
                next_snapshot, now=next_now, confirmation_state=state
            )
            state = result["confirmation_state"]
        self.assertEqual(result["decision"], "CALL BUY")
        self.assertEqual(result["layers"]["confirmation"]["state"], "CONFIRMED")

    def test_refresh_gap_restarts_confirmation(self):
        first = evaluate_five_layer_signal(self.snapshot, now=self.now)
        next_now = self.now + timedelta(seconds=700)
        next_snapshot = dict(self.snapshot)
        next_snapshot["observed_at"] = next_now.isoformat()
        next_snapshot["option_chain"] = [dict(self.snapshot["option_chain"][0], timestamp=next_now.isoformat())]
        result = evaluate_five_layer_signal(
            next_snapshot, now=next_now, confirmation_state=first["confirmation_state"]
        )
        self.assertEqual(result["decision"], "WAIT")
        self.assertEqual(result["layers"]["confirmation"]["state"], "CONFIRMING")

    def test_conflicting_timeframes_block_signal(self):
        self.snapshot["timeframe_closes"]["15m"] = [22010, 22000, 21990, 21980, 21970]
        result = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertEqual(result["decision"], "WAIT")
        self.assertFalse(result["layers"]["trend_sentiment"]["pass"])

    def test_indicator_alignment_blocks_conflicting_ema_or_macd(self):
        self.snapshot["indicators"] = {
            "ema_fast_8": 22010,
            "ema_slow_21": 22000,
            "rsi_14": 61,
            "macd_histogram": 2.5,
            "vwap": 21980,
        }
        aligned = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertTrue(aligned["layers"]["trend_sentiment"]["pass"])

        self.snapshot["indicators"]["ema_fast_8"] = 21990
        self.snapshot["indicators"]["ema_slow_21"] = 22000
        conflicted = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertFalse(conflicted["layers"]["trend_sentiment"]["pass"])
        self.assertEqual(conflicted["decision"], "WAIT")

    def test_commodity_futures_signal_requires_ten_minute_confirmation(self):
        snapshot = {
            "observed_at": self.now.isoformat(),
            "underlying_ltp": 100.0,
            "sentiment_score": 0.55,
            "timeframe_closes": {
                "5m": [90, 92, 94, 97, 100],
                "15m": [88, 90, 93, 96, 100],
                "1h": [85, 89, 92, 96, 100],
            },
            "indicators": {
                "ema_fast_8": 101.0, "ema_slow_21": 99.0,
                "rsi_14": 60.0, "macd_histogram": 1.5,
                "underlying_atr_14": 2.0, "vwap": 95.0,
            },
            "order_flow": {
                "bid": 99.9, "ask": 100.1, "ltp": 100.0,
                "buy_volume": 600, "sell_volume": 400,
            },
            "contract": {
                "symbol": "GOLD26OCTFUT",
                "expiry": (self.now.date() + timedelta(days=10)).isoformat(),
                "volume": 12000, "oi": 200000, "lot_size": 10,
            },
        }
        result = evaluate_futures_signal(snapshot, now=self.now)
        self.assertEqual(result["decision"], "WAIT")
        self.assertEqual(result["candidate_decision"], "BUY FUTURE")
        self.assertEqual(result["signal_stability"]["state"], "CONFIRMING")
        state = result["confirmation_state"]
        for elapsed in range(30, 631, 30):
            next_now = self.now + timedelta(seconds=elapsed)
            next_snapshot = dict(snapshot, observed_at=next_now.isoformat())
            result = evaluate_futures_signal(next_snapshot, now=next_now, confirmation_state=state)
            state = result["confirmation_state"]
        self.assertEqual(result["decision"], "BUY FUTURE")
        self.assertEqual(result["signal_stability"]["state"], "CONFIRMED")
        self.assertFalse(result["order_placement_enabled"])

    def test_wide_option_spread_blocks_contract_selection(self):
        self.snapshot["option_chain"][0]["bid"] = 90
        self.snapshot["option_chain"][0]["ask"] = 110
        self.snapshot["option_chain"][0]["ltp"] = 100
        result = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertEqual(result["decision"], "WAIT")
        self.assertFalse(result["layers"]["option_selection"]["pass"])

    def test_missing_option_atr_blocks_trade_levels(self):
        del self.snapshot["option_chain"][0]["option_atr"]
        result = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertEqual(result["decision"], "WAIT")
        self.assertFalse(result["layers"]["risk_levels"]["pass"])
        self.assertIsNone(result["stop_loss"])

    def test_invalid_order_flow_blocks_signal(self):
        self.snapshot["order_flow"]["ask"] = 99.0
        result = evaluate_five_layer_signal(self.snapshot, now=self.now)
        self.assertEqual(result["decision"], "WAIT")
        self.assertFalse(result["layers"]["order_flow"]["pass"])


if __name__ == "__main__":
    unittest.main()
