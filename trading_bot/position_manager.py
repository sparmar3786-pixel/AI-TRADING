from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class PaperPosition:
    symbol: str
    side: int  # 1 long, -1 short
    quantity: int
    entry: float
    stop_loss: float
    initial_risk: float
    levels_done: list[int] = field(default_factory=list)
    realized_pnl: float = 0.0
    closed: bool = False

    def __post_init__(self):
        if self.side not in (-1, 1) or self.quantity <= 0 or self.entry <= 0 or self.initial_risk <= 0:
            raise ValueError('Invalid paper position')

class PaperPositionManager:
    """Pure simulation of partial exits/trailing stops; it never submits orders."""
    def __init__(self, profit_table: list[dict[str, Any]] | None = None, lot_size: int = 1):
        self.profit_table = profit_table or [
            {'r_multiple': 0.8, 'exit_pct': 30, 'trail_after': False},
            {'r_multiple': 1.5, 'exit_pct': 40, 'trail_after': True},
            {'r_multiple': 2.5, 'exit_pct': 100, 'trail_after': True},
        ]
        self.lot_size = max(1, int(lot_size))

    def update(self, position: PaperPosition, ltp: float) -> dict[str, Any]:
        if position.closed:
            return {'status': 'closed', 'realized_pnl': position.realized_pnl, 'remaining_quantity': 0, 'orders_sent': False}
        price = float(ltp)
        if price <= 0:
            return {'status': 'blocked', 'reason': 'invalid_ltp', 'orders_sent': False}
        if (position.side == 1 and price <= position.stop_loss) or (position.side == -1 and price >= position.stop_loss):
            self._close_quantity(position, position.quantity, price)
            position.closed = True
            return {'status': 'closed', 'reason': 'STOPLOSS', 'realized_pnl': position.realized_pnl, 'remaining_quantity': 0, 'orders_sent': False}
        events = []
        for index, level in enumerate(self.profit_table):
            if index in position.levels_done or position.closed:
                continue
            r = float(level.get('r_multiple', 1.0))
            target = position.entry + position.side * r * position.initial_risk
            hit = price >= target if position.side == 1 else price <= target
            if not hit:
                continue
            if bool(level.get('trail_after', False)):
                offset = max(r - 0.25, 0.0) * position.initial_risk
                candidate = position.entry + position.side * offset
                position.stop_loss = max(position.stop_loss, candidate) if position.side == 1 else min(position.stop_loss, candidate)
            pct = max(0.0, min(100.0, float(level.get('exit_pct', 100))))
            qty = position.quantity if pct >= 100 else int(position.quantity * pct / 100.0)
            qty = (qty // self.lot_size) * self.lot_size
            if 0 < position.quantity - qty < self.lot_size:
                qty = position.quantity
            if qty <= 0:
                position.levels_done.append(index)
                continue
            self._close_quantity(position, qty, price)
            position.levels_done.append(index)
            events.append({'level': index, 'r_multiple': r, 'exit_quantity': qty, 'price': price, 'stop_loss': position.stop_loss})
        if position.quantity <= 0:
            position.closed = True
        return {'status': 'closed' if position.closed else 'open', 'events': events,
                'realized_pnl': position.realized_pnl, 'remaining_quantity': position.quantity,
                'stop_loss': position.stop_loss, 'orders_sent': False}

    @staticmethod
    def _close_quantity(position: PaperPosition, quantity: int, price: float) -> None:
        quantity = min(max(0, int(quantity)), position.quantity)
        position.realized_pnl += position.side * (float(price) - position.entry) * quantity
        position.quantity -= quantity
