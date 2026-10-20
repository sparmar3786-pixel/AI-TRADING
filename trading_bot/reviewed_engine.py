from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date
import json, math, sqlite3, threading

@dataclass
class PaperState:
    day: str
    starting_capital: float
    realized_pnl: float = 0.0
    open_pnl: float = 0.0
    trades_today: int = 0
    halt: str | None = None
    position: dict | None = None

class ReviewedPaperEngine:
    """Paper-only risk and position lifecycle. It has no broker order API."""
    def __init__(self, db_path: str, starting_capital: float = 100000,
                 profit_lock_pct: float = 15, max_loss_pct: float = 5,
                 max_trades: int = 10, lot_size: int = 1):
        vals = (starting_capital, profit_lock_pct, max_loss_pct)
        if any(not math.isfinite(float(v)) or float(v) <= 0 for v in vals):
            raise ValueError('Risk values must be finite and positive')
        if max_trades < 1 or lot_size < 1:
            raise ValueError('max_trades and lot_size must be positive')
        self.db_path, self.capital = db_path, float(starting_capital)
        self.profit_pct, self.loss_pct = float(profit_lock_pct), float(max_loss_pct)
        self.max_trades, self.lot_size = int(max_trades), int(lot_size)
        self.lock = threading.RLock()
        with sqlite3.connect(self.db_path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS paper_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS paper_events (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            row = db.execute('SELECT payload FROM paper_state WHERE id=1').fetchone()
        self.state = PaperState(date.today().isoformat(), self.capital) if row is None else PaperState(**json.loads(row[0]))
        if self.state.starting_capital != self.capital:
            raise RuntimeError('Capital config differs from persisted state; reconcile offline first')
        self._save()

    def _save(self, event=None):
        with sqlite3.connect(self.db_path) as db:
            db.execute('INSERT OR REPLACE INTO paper_state(id,payload) VALUES(1,?)',
                       (json.dumps(asdict(self.state), allow_nan=False),))
            if event:
                db.execute('INSERT INTO paper_events(payload) VALUES(?)',
                           (json.dumps(event, allow_nan=False),))

    @property
    def net_pnl(self):
        return self.state.realized_pnl + self.state.open_pnl

    def _apply_locks(self):
        if self.net_pnl <= -self.capital*self.loss_pct/100 and self.state.halt is None:
            self.state.halt = 'DAILY_MAX_LOSS'
        elif self.net_pnl >= self.capital*self.profit_pct/100 and self.state.halt is None:
            self.state.halt = 'DAILY_PROFIT_LOCK'
        if self.state.halt and self.state.position:
            self._close(self.state.position['qty'], self.state.position['last_price'], self.state.halt)

    def can_open(self):
        return self.state.halt is None and self.state.position is None and self.state.trades_today < self.max_trades

    def enter(self, symbol: str, qty: int, lot_size: int, price: float, stop: float, targets=None):
        with self.lock:
            if not self.can_open():
                return False
            if not symbol or not all(math.isfinite(float(x)) for x in (price, stop)) or price <= 0 or stop <= 0 or stop >= price:
                raise ValueError('Invalid long-only paper entry')
            if qty <= 0 or lot_size <= 0 or qty % lot_size or lot_size != self.lot_size:
                raise ValueError('Quantity must be a valid configured lot multiple')
            self.state.position = {
                'symbol': symbol, 'qty': int(qty), 'initial_qty': int(qty),
                'entry': float(price), 'stop': float(stop), 'last_price': float(price),
                'targets': targets or [
                    {'price': price+(price-stop)*r, 'cumulative_pct': pct}
                    for r, pct in ((1, 30), (1.5, 70), (2.5, 100))
                ],
                'done': [], 'realized_trade': 0.0
            }
            self.state.trades_today += 1
            self.state.open_pnl = 0.0
            self._save({'type': 'PAPER_ENTRY', 'symbol': symbol, 'qty': qty, 'price': price, 'orders_sent': False})
            return True

    def _close(self, qty, price, reason):
        p = self.state.position
        if not p or qty <= 0 or qty > p['qty'] or qty % self.lot_size:
            return
        pnl = (float(price)-p['entry'])*qty
        self.state.realized_pnl += pnl
        p['realized_trade'] += pnl
        p['qty'] -= qty
        self.state.open_pnl = (p['last_price']-p['entry'])*p['qty'] if p['qty'] else 0.0
        self._save({'type': 'PAPER_EXIT', 'qty': qty, 'price': price, 'pnl': pnl,
                    'reason': reason, 'orders_sent': False})
        if p['qty'] == 0:
            self.state.position = None

    def on_quote(self, price: float, quote_age_seconds: float):
        with self.lock:
            if (not math.isfinite(float(price)) or price <= 0 or
                not math.isfinite(float(quote_age_seconds)) or not 0 <= quote_age_seconds <= 10):
                return {'status': 'WAIT', 'reason': 'STALE_OR_INVALID_QUOTE', 'orders_sent': False}
            p = self.state.position
            if p:
                p['last_price'] = float(price)
                self.state.open_pnl = (float(price)-p['entry'])*p['qty']
            self._apply_locks()
            p = self.state.position
            if p:
                if price <= p['stop']:
                    self._close(p['qty'], price, 'STOPLOSS')
                else:
                    for i, target in enumerate(p['targets']):
                        p = self.state.position
                        if not p or i in p['done'] or price < float(target['price']):
                            continue
                        desired = (p['initial_qty']*int(target['cumulative_pct'])//100//self.lot_size)*self.lot_size
                        already = p['initial_qty']-p['qty']
                        qty = min(p['qty'], max(0, desired-already))
                        if qty:
                            self._close(qty, price, 'TARGET_'+str(i))
                        p = self.state.position
                        if p:
                            p['done'].append(i)
            self._apply_locks()
            self._save()
            return {'status': 'HALTED' if self.state.halt else ('OPEN' if self.state.position else 'FLAT'),
                    'net_pnl': self.net_pnl, 'halt': self.state.halt,
                    'remaining_qty': self.state.position['qty'] if self.state.position else 0,
                    'orders_sent': False}

    def kill(self):
        with self.lock:
            self.state.halt = 'MANUAL_KILL'
            if self.state.position:
                self._close(self.state.position['qty'], self.state.position['last_price'], 'MANUAL_KILL')
            self._save({'type': 'PAPER_KILL', 'orders_sent': False})

    def snapshot(self):
        return {'mode': 'paper', 'orders_enabled': False, 'state': asdict(self.state),
                'net_pnl': self.net_pnl, 'can_open': self.can_open()}
