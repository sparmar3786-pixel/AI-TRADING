import unittest

from backend.app.main import _apply_strategy_confluence_filter


class StrategyQuantConfluenceGateTests(unittest.TestCase):
    def _result(self):
        return {
            "decision": "CALL BUY",
            "candidate_decision": "CALL BUY",
            "option_type": "CALL",
            "option_side": "CE",
            "strike": 25000,
            "expiry": "2026-10-29",
            "entry": 101.0,
            "stop_loss": 96.0,
            "target": 111.0,
            "reasons": [],
            "signal_stability": {"state": "CONFIRMED"},
            "trade_plan": {
                "selection_grade": "A", "strike": 25000, "expiry": "2026-10-29",
                "entry": 101.0, "stop_loss": 96.0, "target": 111.0,
            },
            "five_layer_engine": {"decision": "CALL BUY"},
            "live_validation": {"verdict": "PASS", "blocks": []},
        }

    def test_matching_strategy_consensus_preserves_quant_setup(self):
        result = self._result()
        suite = {"status": "ok", "signal": "LONG", "votes": {"LONG": 4, "SHORT": 1}}
        filtered = _apply_strategy_confluence_filter(result, suite, "strategy-test")
        self.assertEqual(filtered["decision"], "CALL BUY")
        self.assertTrue(filtered["strategy_filter"]["pass"])
        self.assertEqual(filtered["entry"], 101.0)
        self.assertEqual(filtered["exit"], 111.0)
        self.assertEqual(filtered["exit_semantics"], "target price reference; signal-only, no order placement")
        self.assertEqual(filtered["trade_plan"]["target"], 111.0)
        self.assertEqual(filtered["five_layer_engine"]["decision"], "CALL BUY")

    def test_conflicting_strategy_consensus_blocks_and_clears_actionable_levels(self):
        result = self._result()
        suite = {"status": "ok", "signal": "SHORT", "votes": {"LONG": 1, "SHORT": 5}}
        filtered = _apply_strategy_confluence_filter(result, suite, "strategy-test")
        self.assertEqual(filtered["decision"], "WAIT")
        self.assertFalse(filtered["strategy_filter"]["pass"])
        self.assertEqual(filtered["strategy_filter"]["state"], "BLOCKED")
        self.assertIsNone(filtered["strike"])
        self.assertIsNone(filtered["entry"])
        self.assertIsNone(filtered["exit"])
        self.assertIsNone(filtered["stop_loss"])
        self.assertIsNone(filtered["target"])
        self.assertEqual(filtered["candidate_setup"]["status"], "BLOCKED_NOT_ACTIONABLE")
        self.assertEqual(filtered["trade_plan"]["selection_grade"], "WAIT")
        self.assertEqual(filtered["five_layer_engine"]["decision"], "WAIT")
        self.assertEqual(filtered["live_validation"]["verdict"], "BLOCKED")
        self.assertIn("STRATEGY_CONFLUENCE_BLOCKED", filtered["live_validation"]["blocks"])

    def test_weak_consensus_blocks_candidate(self):
        result = self._result()
        suite = {"status": "ok", "signal": "LONG", "votes": {"LONG": 2, "SHORT": 0}}
        filtered = _apply_strategy_confluence_filter(result, suite, "strategy-test")
        self.assertEqual(filtered["decision"], "WAIT")
        self.assertFalse(filtered["strategy_filter"]["pass"])
        self.assertIsNone(filtered["entry"])

    def test_wait_without_quant_candidate_stays_wait(self):
        result = self._result()
        result["decision"] = "WAIT"
        result["candidate_decision"] = "WAIT"
        suite = {"status": "ok", "signal": "LONG", "votes": {"LONG": 5, "SHORT": 0}}
        filtered = _apply_strategy_confluence_filter(result, suite, "strategy-test")
        self.assertEqual(filtered["decision"], "WAIT")
        self.assertEqual(filtered["strategy_filter"]["state"], "NO_QUANT_CANDIDATE")
        self.assertNotIn("candidate_setup", filtered)


if __name__ == "__main__":
    unittest.main()
