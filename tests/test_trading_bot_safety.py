from trading_bot.risk import DailyRiskManager


def test_daily_profit_lock_blocks_new_entries_and_tracks_open_pnl():
    risk = DailyRiskManager(starting_capital=100000, profit_lock_pct=15, max_loss_pct=5, max_trades=10)
    assert risk.can_open()
    risk.mark_open_pnl(15000)
    assert risk.profit_locked
    assert not risk.can_open()


def test_daily_loss_limit_blocks_new_entries():
    risk = DailyRiskManager(starting_capital=100000, profit_lock_pct=15, max_loss_pct=5, max_trades=10)
    risk.add_realized_pnl(-5000)
    assert risk.max_loss_hit
    assert not risk.can_open()


def test_max_trade_count_blocks_new_entries():
    risk = DailyRiskManager(starting_capital=100000, max_trades=1)
    assert risk.register_trade()
    assert not risk.register_trade()
