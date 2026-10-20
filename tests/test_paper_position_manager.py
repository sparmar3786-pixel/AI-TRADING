import unittest
from trading_bot.position_manager import PaperPosition, PaperPositionManager
from trading_bot.optimizer import ConservativeOptimizer


class PaperPositionTests(unittest.TestCase):
    def test_profit_table_partial_exit_and_trailing_stop_are_simulated(self):
        position = PaperPosition(symbol='NIFTY', side=1, quantity=10, entry=100.0, stop_loss=90.0, initial_risk=10.0)
        manager = PaperPositionManager(lot_size=1)
        result = manager.update(position, 108.0)
        self.assertEqual(result['status'], 'open')
        self.assertEqual(result['remaining_quantity'], 7)
        self.assertGreaterEqual(position.realized_pnl, 0.0)
        self.assertFalse(result['orders_sent'])

    def test_stop_loss_closes_simulated_position_without_order(self):
        position = PaperPosition(symbol='NIFTY', side=1, quantity=2, entry=100.0, stop_loss=95.0, initial_risk=5.0)
        result = PaperPositionManager().update(position, 94.0)
        self.assertEqual(result['status'], 'closed')
        self.assertEqual(result['remaining_quantity'], 0)
        self.assertFalse(result['orders_sent'])

    def test_optimizer_only_returns_bounded_candidate(self):
        current = {'ema_fast': 9, 'ema_slow': 21, 'entry_score_threshold': 3}
        candidate = ConservativeOptimizer().candidate(current, seed=3)
        self.assertLess(candidate['ema_fast'], candidate['ema_slow'])
        self.assertGreaterEqual(candidate['entry_score_threshold'], 3)
        self.assertLessEqual(candidate['entry_score_threshold'], 5)
        self.assertEqual(current, {'ema_fast': 9, 'ema_slow': 21, 'entry_score_threshold': 3})


if __name__ == '__main__':
    unittest.main()
