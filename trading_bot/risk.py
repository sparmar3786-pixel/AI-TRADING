from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass
class DailyRiskManager:
    starting_capital: float = 100000.0
    profit_lock_pct: float = 15.0
    max_loss_pct: float = 5.0
    max_trades: int = 10
    realized_pnl: float = 0.0
    open_pnl: float = 0.0
    trades_today: int = 0

    def __post_init__(self):
        if self.starting_capital <= 0 or self.profit_lock_pct <= 0 or self.max_loss_pct <= 0 or self.max_trades < 1:
            raise ValueError('Invalid risk configuration')

    @property
    def net_pnl(self) -> float:
        return float(self.realized_pnl + self.open_pnl)

    @property
    def profit_locked(self) -> bool:
        return self.net_pnl >= self.starting_capital * self.profit_lock_pct / 100.0

    @property
    def max_loss_hit(self) -> bool:
        return self.net_pnl <= -self.starting_capital * self.max_loss_pct / 100.0

    def can_open(self) -> bool:
        return not self.profit_locked and not self.max_loss_hit and self.trades_today < self.max_trades

    def register_trade(self) -> bool:
        if not self.can_open():
            return False
        self.trades_today += 1
        return True

    def add_realized_pnl(self, pnl: float) -> None:
        self.realized_pnl += float(pnl)

    def mark_open_pnl(self, pnl: float) -> None:
        self.open_pnl = float(pnl)

    def as_dict(self):
        return {**asdict(self), 'net_pnl': self.net_pnl, 'profit_locked': self.profit_locked,
                'max_loss_hit': self.max_loss_hit, 'can_open': self.can_open(),
                'profit_lock_amount': self.starting_capital * self.profit_lock_pct / 100.0,
                'max_loss_amount': self.starting_capital * self.max_loss_pct / 100.0}
