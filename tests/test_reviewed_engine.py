import pytest
from trading_bot.reviewed_engine import ReviewedPaperEngine

def make(tmp_path, **kw):
    return ReviewedPaperEngine(str(tmp_path/'db.sqlite'), **kw)

def test_paper_entry_and_no_orders(tmp_path):
    e = make(tmp_path, lot_size=10)
    assert e.enter('TEST', 100, 10, 100, 90)
    r = e.on_quote(101, 0)
    assert r['status'] == 'OPEN' and r['orders_sent'] is False

def test_stale_quote_blocks_without_fabricated_exit(tmp_path):
    e = make(tmp_path, lot_size=10)
    e.enter('TEST', 100, 10, 100, 90)
    r = e.on_quote(80, 30)
    assert r['status'] == 'WAIT' and e.state.position['qty'] == 100

def test_profit_lock_closes_and_latches(tmp_path):
    e = make(tmp_path, starting_capital=1000, profit_lock_pct=1, lot_size=10)
    e.enter('TEST', 100, 10, 100, 90)
    e.on_quote(120, 0)
    assert e.state.halt == 'DAILY_PROFIT_LOCK' and e.state.position is None and not e.can_open()

def test_loss_lock_closes(tmp_path):
    e = make(tmp_path, starting_capital=1000, max_loss_pct=1, lot_size=10)
    e.enter('TEST', 100, 10, 100, 90)
    e.on_quote(80, 0)
    assert e.state.halt == 'DAILY_MAX_LOSS' and e.state.position is None

def test_partial_targets_are_cumulative(tmp_path):
    e = make(tmp_path, lot_size=10)
    e.enter('TEST', 100, 10, 100, 90)
    e.on_quote(110, 0)
    assert e.state.position['qty'] == 70
    e.on_quote(115, 0)
    assert e.state.position['qty'] == 30
    e.on_quote(125, 0)
    assert e.state.position is None

def test_kill_latches_and_closes(tmp_path):
    e = make(tmp_path, lot_size=10)
    e.enter('TEST', 100, 10, 100, 90)
    e.kill()
    assert e.state.halt == 'MANUAL_KILL' and e.state.position is None and not e.can_open()

def test_restart_persists_halt(tmp_path):
    path = str(tmp_path/'db.sqlite')
    ReviewedPaperEngine(path, lot_size=10).kill()
    again = ReviewedPaperEngine(path, lot_size=10)
    assert again.state.halt == 'MANUAL_KILL'

def test_bad_lot_rejected(tmp_path):
    e = make(tmp_path, lot_size=10)
    with pytest.raises(ValueError):
        e.enter('TEST', 13, 10, 100, 90)
