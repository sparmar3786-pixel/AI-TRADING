import os
import tempfile
import unittest
from unittest.mock import patch

from backend.app.main import _paper_performance_summary, _signal_outcome_report, _signal_outcomes_memory, _update_signal_outcomes


class PaperPerformanceSummaryTests(unittest.TestCase):
    def test_reports_win_loss_target_stop_and_per_instrument(self):
        rows = [
            {"trade_id": "1", "instrument": "NIFTY", "status": "CLOSED", "gross_r": 2.0, "net_r": 1.96, "exit_reason": "TARGET", "net_pnl_inr": 1470.0, "costs_explicit": True},
            {"trade_id": "2", "instrument": "NIFTY", "status": "CLOSED", "gross_r": -1.0, "net_r": -1.04, "exit_reason": "STOP_LOSS", "net_pnl_inr": -780.0, "costs_explicit": True},
            {"trade_id": "3", "instrument": "BANKNIFTY", "status": "CLOSED", "gross_r": 0.5, "net_r": 0.46, "exit_reason": "TARGET_HIT", "net_pnl_inr": 690.0, "costs_explicit": True},
            {"trade_id": "4", "instrument": "CRUDEOIL", "status": "CLOSED", "gross_r": -1.0, "net_r": -1.04, "exit_reason": "SL", "net_pnl_inr": -520.0, "costs_explicit": True},
            {"trade_id": "5", "instrument": "NIFTY", "status": "OPEN", "net_r": None},
        ]
        report = _paper_performance_summary(rows)
        self.assertEqual(report["trade_count"], 4)
        self.assertEqual(report["metrics"]["win_count"], 2)
        self.assertEqual(report["metrics"]["loss_count"], 2)
        self.assertAlmostEqual(report["metrics"]["win_rate"], 0.5)
        self.assertAlmostEqual(report["metrics"]["loss_rate"], 0.5)
        self.assertEqual(report["metrics"]["target_hits"], 2)
        self.assertEqual(report["metrics"]["stop_loss_hits"], 2)
        self.assertAlmostEqual(report["metrics"]["net_pnl_inr"], 860.0)
        self.assertEqual(report["by_instrument"]["NIFTY"]["trade_count"], 2)
        self.assertEqual(report["by_instrument"]["BANKNIFTY"]["target_hits"], 1)
        self.assertEqual(report["by_instrument"]["CRUDEOIL"]["stop_loss_hits"], 1)
        self.assertEqual(report["metrics"]["open_trade_count"], 1)

    def test_does_not_fabricate_rupee_pnl_when_missing(self):
        report = _paper_performance_summary([
            {"trade_id": "1", "instrument": "NIFTY", "status": "CLOSED", "gross_r": 1.0, "net_r": 0.96, "exit_reason": "MANUAL", "net_pnl_inr": 100.0, "slippage_inr": 0.0, "brokerage_inr": 0.0, "other_costs_inr": 0.0},
        ])
        self.assertIsNone(report["metrics"]["net_pnl_inr"])
        self.assertEqual(report["metrics"]["pnl_status"], "NOT_AVAILABLE_FOR_ALL_TRADES")

    def test_confirmed_signal_is_shadow_tracked_until_target(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = os.path.join(directory, "signal_outcomes.json")
            with patch.dict(os.environ, {"SIGNAL_OUTCOMES_FILE": ledger_path}, clear=False):
                _signal_outcomes_memory.clear()
                signal = {
                    "decision": "CALL BUY", "option_type": "CALL", "strike": 25000,
                    "expiry": "2026-10-29", "entry": 100.0, "stop_loss": 90.0, "target": 120.0,
                    "data_fresh": True, "live_validation": {"verdict": "PASS"},
                    "signal_stability": {"state": "CONFIRMED"},
                    "trade_plan": {"lot_size": 50, "quantity": 1},
                }
                market = {"NIFTY": {
                    "live": True, "option_chain": [{
                        "strike": 25000, "expiry": "2026-10-29", "option_type": "CALL",
                        "ltp": 100.0, "age_seconds": 2, "live": True,
                        "source_timestamp": "2026-10-15T08:00:00+00:00",
                    }],
                }}
                first = _update_signal_outcomes({"NIFTY": signal}, market)
                self.assertEqual(first["metrics"]["open_count"], 1)
                market["NIFTY"]["option_chain"][0]["ltp"] = 121.0
                second = _update_signal_outcomes({}, market)
                self.assertEqual(second["metrics"]["closed_count"], 1)
                self.assertEqual(second["metrics"]["target_hits"], 1)
                self.assertEqual(second["metrics"]["stop_loss_hits"], 0)
                self.assertEqual(second["metrics"]["gross_points_total"], 20.0)
                self.assertIsNone(second["metrics"]["net_pnl_inr"])
                self.assertEqual(second["accuracy_status"], "OBSERVED_QUOTE_OUTCOMES")
                _signal_outcomes_memory.clear()

    def test_signal_win_rate_requires_explicit_fee_adjusted_pnl(self):
        rows = [
            {"outcome_id": "1", "index": "NIFTY", "status": "CLOSED", "exit_reason": "TARGET",
             "entry_price": 100, "exit_price": 120, "net_pnl_inr": 900,
             "pnl_status": "RECORDED", "costs_inr": {"brokerage_inr": 50, "slippage_inr": 30, "other_costs_inr": 20}},
            {"outcome_id": "2", "index": "NIFTY", "status": "CLOSED", "exit_reason": "STOP_LOSS",
             "entry_price": 100, "exit_price": 90, "net_pnl_inr": None,
             "pnl_status": "NOT_AVAILABLE_WITHOUT_QUANTITY_AND_ALL_COSTS"},
        ]
        report = _signal_outcome_report(rows, {"status": "OK"})
        metrics = report["metrics"]
        self.assertEqual(metrics["target_hits"], 1)
        self.assertEqual(metrics["stop_loss_hits"], 1)
        self.assertIsNone(metrics["win_rate"])
        self.assertIsNone(metrics["loss_rate"])
        self.assertIsNone(metrics["net_pnl_inr"])
        self.assertEqual(metrics["net_pnl_coverage_count"], 1)
        self.assertEqual(report["by_instrument"]["NIFTY"]["closed_count"], 2)
        self.assertIn("BANKNIFTY", report["by_instrument"])
        self.assertEqual(report["mcx"]["status"], "NOT_TRACKED_BY_INDEX_OPTION_SIGNAL_ENGINE")
        self.assertEqual(report["persistence"]["status"], "OK")

    def test_empty_history_is_explicitly_unverified(self):
        report = _paper_performance_summary([])
        self.assertEqual(report["trade_count"], 0)
        self.assertIsNone(report["metrics"]["win_rate"])
        self.assertEqual(report["accuracy_status"], "UNVERIFIED_NO_CLOSED_TRADES")


if __name__ == "__main__":
    unittest.main()
