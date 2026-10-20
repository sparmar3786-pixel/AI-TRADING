import unittest
from trading_bot.risk import DailyRiskManager
from trading_bot.advisor import MultiLevelAdvisor
import numpy as np


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

    def test_advisor_waits_when_regime_history_is_insufficient(self):
        rng = np.random.default_rng(5)
        close = 25000 + np.cumsum(rng.normal(0, 8, 80))
        candles = []
        for index, price in enumerate(close):
            candles.append({'open': float(price - 1), 'high': float(price + 5),
                            'low': float(price - 5), 'close': float(price),
                            'volume': float(1000 + index * 3)})
        result = MultiLevelAdvisor().evaluate(candles)
        self.assertEqual(result['decision'], 'WAIT')
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['reason'], 'regime_unavailable_or_high_volatility')
        self.assertIsNone(result['entry'])


if __name__ == '__main__':
    unittest.main()
