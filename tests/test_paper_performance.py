import unittest

from backend.app.main import _paper_performance_summary


class PaperPerformanceSummaryTests(unittest.TestCase):
    def test_reports_win_loss_target_stop_and_per_instrument(self):
        rows = [
            {"trade_id": "1", "instrument": "NIFTY", "status": "CLOSED", "gross_r": 2.0, "net_r": 1.96, "exit_reason": "TARGET", "net_pnl_inr": 1470.0},
            {"trade_id": "2", "instrument": "NIFTY", "status": "CLOSED", "gross_r": -1.0, "net_r": -1.04, "exit_reason": "STOP_LOSS", "net_pnl_inr": -780.0},
            {"trade_id": "3", "instrument": "BANKNIFTY", "status": "CLOSED", "gross_r": 0.5, "net_r": 0.46, "exit_reason": "TARGET_HIT", "net_pnl_inr": 690.0},
            {"trade_id": "4", "instrument": "CRUDEOIL", "status": "CLOSED", "gross_r": -1.0, "net_r": -1.04, "exit_reason": "SL", "net_pnl_inr": -520.0},
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
            {"trade_id": "1", "instrument": "NIFTY", "status": "CLOSED", "gross_r": 1.0, "net_r": 0.96, "exit_reason": "MANUAL"},
        ])
        self.assertIsNone(report["metrics"]["net_pnl_inr"])
        self.assertEqual(report["metrics"]["pnl_status"], "NOT_AVAILABLE_FOR_ALL_TRADES")

    def test_empty_history_is_explicitly_unverified(self):
        report = _paper_performance_summary([])
        self.assertEqual(report["trade_count"], 0)
        self.assertIsNone(report["metrics"]["win_rate"])
        self.assertEqual(report["accuracy_status"], "UNVERIFIED_NO_CLOSED_TRADES")


if __name__ == "__main__":
    unittest.main()
