import unittest
from trading_bot.risk import DailyRiskManager


class PaperRiskTests(unittest.TestCase):
    def test_daily_profit_lock_blocks_new_entries_and_tracks_open_pnl(self):
        risk = DailyRiskManager(starting_capital=100000, profit_lock_pct=15, max_loss_pct=5, max_trades=10)
        self.assertTrue(risk.can_open())
        risk.mark_open_pnl(15000)
        self.assertTrue(risk.profit_locked)
        self.assertFalse(risk.can_open())

    def test_daily_loss_limit_blocks_new_entries(self):
        risk = DailyRiskManager(starting_capital=100000, profit_lock_pct=15, max_loss_pct=5, max_trades=10)
        risk.add_realized_pnl(-5000)
        self.assertTrue(risk.max_loss_hit)
        self.assertFalse(risk.can_open())

    def test_max_trade_count_blocks_new_entries(self):
        risk = DailyRiskManager(starting_capital=100000, max_trades=1)
        self.assertTrue(risk.register_trade())
        self.assertFalse(risk.register_trade())


if __name__ == '__main__':
    unittest.main()
