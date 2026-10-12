"""
Risk Manager - The Most Important File
========================================
This is what keeps you in the game. Everything else is secondary.

Rules (non-negotiable):
1. Never risk more than 2% per trade
2. Never risk more than 6% per day
3. Stop trading after 3 consecutive losses
4. Reduce size by 50% during drawdown
5. No trading after big wins (overconfidence)

"The goal is not to make money. The goal is to not lose money."
"""

import os
import json
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import math


class RiskStatus(Enum):
    """Current risk status."""
    GREEN = "green"       # All systems go
    YELLOW = "yellow"     # Caution - reduced size
    RED = "red"           # Stop trading today
    LOCKED = "locked"     # Account locked - review needed


@dataclass
class Trade:
    """Record of a trade."""
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size: int
    pnl: float
    r_multiple: float
    timestamp: datetime
    trade_id: str = ""

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry': self.entry_price,
            'exit': self.exit_price,
            'size': self.size,
            'pnl': self.pnl,
            'r_multiple': self.r_multiple,
            'timestamp': self.timestamp.isoformat(),
            'trade_id': self.trade_id,
        }


@dataclass
class DailyStats:
    """Daily trading statistics."""
    date: date
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_pnl: float = 0.0
    total_r: float = 0.0
    consecutive_losses: int = 0
    max_drawdown: float = 0.0


@dataclass
class RiskDecision:
    """Risk manager's decision."""
    can_trade: bool
    status: RiskStatus
    position_size_pct: float  # Max position size allowed
    max_risk_dollars: float
    reasoning: str
    warnings: List[str] = field(default_factory=list)


class RiskManager:
    """
    Manages all risk for the trading account.

    This is the gatekeeper. No trade happens without its approval.
    """

    # Fixed rules - DO NOT CHANGE
    MAX_RISK_PER_TRADE = 0.02      # 2% max per trade
    MAX_RISK_PER_DAY = 0.06        # 6% max per day
    MAX_CONSECUTIVE_LOSSES = 3     # Stop after 3 losses
    DRAWDOWN_REDUCTION = 0.50     # Cut size by 50% in drawdown
    DRAWDOWN_THRESHOLD = 0.10     # 10% drawdown triggers reduction
    COOLING_OFF_AFTER_BIG_WIN = 2  # Hours to wait after 3R+ win

    def __init__(
        self,
        account_balance: float,
        data_dir: str = None,
    ):
        self.account_balance = account_balance
        self.starting_balance = account_balance
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'risk_data'
        )
        os.makedirs(self.data_dir, exist_ok=True)

        self.today_stats = DailyStats(date=date.today())
        self.recent_trades: List[Trade] = []

        self._load_state()

    def _load_state(self):
        """Load persisted state."""
        state_file = os.path.join(self.data_dir, 'risk_state.json')
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state = json.load(f)
                self.account_balance = state.get('account_balance', self.account_balance)
                self.starting_balance = state.get('starting_balance', self.starting_balance)

                # Load today's stats
                if state.get('today_date') == str(date.today()):
                    stats = state.get('today_stats', {})
                    self.today_stats = DailyStats(
                        date=date.today(),
                        trades=stats.get('trades', 0),
                        wins=stats.get('wins', 0),
                        losses=stats.get('losses', 0),
                        gross_pnl=stats.get('gross_pnl', 0),
                        total_r=stats.get('total_r', 0),
                        consecutive_losses=stats.get('consecutive_losses', 0),
                    )

    def _save_state(self):
        """Persist state."""
        state_file = os.path.join(self.data_dir, 'risk_state.json')
        state = {
            'account_balance': self.account_balance,
            'starting_balance': self.starting_balance,
            'today_date': str(date.today()),
            'today_stats': {
                'trades': self.today_stats.trades,
                'wins': self.today_stats.wins,
                'losses': self.today_stats.losses,
                'gross_pnl': self.today_stats.gross_pnl,
                'total_r': self.today_stats.total_r,
                'consecutive_losses': self.today_stats.consecutive_losses,
            },
            'updated_at': datetime.now().isoformat(),
        }
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def can_take_trade(
        self,
        risk_per_share: float,
        entry_price: float,
        direction: str = "LONG",
    ) -> RiskDecision:
        """
        Ask permission to take a trade.

        This is the main function. Call this BEFORE every trade.
        """
        warnings = []

        # Check 1: Daily loss limit
        daily_risk_used = abs(self.today_stats.gross_pnl) / self.account_balance
        if self.today_stats.gross_pnl < 0 and daily_risk_used >= self.MAX_RISK_PER_DAY:
            return RiskDecision(
                can_trade=False,
                status=RiskStatus.RED,
                position_size_pct=0,
                max_risk_dollars=0,
                reasoning=f"Daily loss limit hit ({daily_risk_used:.1%} lost today)",
            )

        # Check 2: Consecutive losses
        if self.today_stats.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            return RiskDecision(
                can_trade=False,
                status=RiskStatus.RED,
                position_size_pct=0,
                max_risk_dollars=0,
                reasoning=f"{self.today_stats.consecutive_losses} consecutive losses - stop trading today",
            )

        # Check 3: Account drawdown
        drawdown = (self.starting_balance - self.account_balance) / self.starting_balance
        if drawdown >= self.DRAWDOWN_THRESHOLD:
            warnings.append(f"Account in {drawdown:.1%} drawdown - size reduced")

        # Check 4: Recent big win (overconfidence protection)
        if self.recent_trades:
            last_trade = self.recent_trades[-1]
            if last_trade.r_multiple >= 3.0:
                hours_since = (datetime.now() - last_trade.timestamp).total_seconds() / 3600
                if hours_since < self.COOLING_OFF_AFTER_BIG_WIN:
                    warnings.append(f"Big win {hours_since:.1f}h ago - stay humble")

        # Calculate allowed position size
        base_risk_pct = self.MAX_RISK_PER_TRADE

        # Reduce for drawdown
        if drawdown >= self.DRAWDOWN_THRESHOLD:
            base_risk_pct *= self.DRAWDOWN_REDUCTION

        # Reduce for consecutive losses (even if under limit)
        if self.today_stats.consecutive_losses == 2:
            base_risk_pct *= 0.75
            warnings.append("2 losses in a row - reducing size")

        # Calculate max risk dollars
        max_risk_dollars = self.account_balance * base_risk_pct

        # Remaining daily budget
        remaining_daily = (self.MAX_RISK_PER_DAY * self.account_balance) - abs(self.today_stats.gross_pnl)
        max_risk_dollars = min(max_risk_dollars, remaining_daily)

        # Determine status
        if warnings:
            status = RiskStatus.YELLOW
        else:
            status = RiskStatus.GREEN

        return RiskDecision(
            can_trade=True,
            status=status,
            position_size_pct=base_risk_pct,
            max_risk_dollars=max_risk_dollars,
            reasoning="Trade approved" + (f" with {len(warnings)} warning(s)" if warnings else ""),
            warnings=warnings,
        )

    def calculate_position_size(
        self,
        entry_price: float,
        stop_price: float,
        risk_decision: RiskDecision = None,
    ) -> Dict:
        """
        Calculate exact position size based on risk.

        Returns shares to buy and dollar risk.
        """
        if risk_decision is None:
            risk_decision = self.can_take_trade(
                risk_per_share=abs(entry_price - stop_price),
                entry_price=entry_price,
            )

        if not risk_decision.can_trade:
            return {
                'shares': 0,
                'dollar_risk': 0,
                'position_value': 0,
                'can_trade': False,
                'reason': risk_decision.reasoning,
            }

        risk_per_share = abs(entry_price - stop_price)

        if risk_per_share <= 0:
            return {
                'shares': 0,
                'dollar_risk': 0,
                'position_value': 0,
                'can_trade': False,
                'reason': 'Invalid stop distance',
            }

        # Calculate shares
        shares = int(risk_decision.max_risk_dollars / risk_per_share)

        # Ensure we can afford it
        position_value = shares * entry_price
        if position_value > self.account_balance * 0.5:  # Max 50% in one position
            shares = int((self.account_balance * 0.5) / entry_price)
            position_value = shares * entry_price

        actual_risk = shares * risk_per_share

        return {
            'shares': shares,
            'dollar_risk': actual_risk,
            'position_value': position_value,
            'risk_percent': actual_risk / self.account_balance,
            'can_trade': shares > 0,
            'reason': 'OK' if shares > 0 else 'Position too small',
        }

    def record_trade(self, trade: Trade):
        """Record a completed trade."""
        self.recent_trades.append(trade)
        if len(self.recent_trades) > 100:
            self.recent_trades = self.recent_trades[-100:]

        # Update today's stats
        self.today_stats.trades += 1
        self.today_stats.gross_pnl += trade.pnl
        self.today_stats.total_r += trade.r_multiple

        if trade.pnl > 0:
            self.today_stats.wins += 1
            self.today_stats.consecutive_losses = 0
        else:
            self.today_stats.losses += 1
            self.today_stats.consecutive_losses += 1

        # Update account balance
        self.account_balance += trade.pnl

        # Log the trade
        self._log_trade(trade)
        self._save_state()

    def _log_trade(self, trade: Trade):
        """Log trade to file."""
        log_file = os.path.join(self.data_dir, f'trades_{date.today()}.json')

        trades = []
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                trades = json.load(f)

        trades.append(trade.to_dict())

        with open(log_file, 'w') as f:
            json.dump(trades, f, indent=2)

    def get_daily_summary(self) -> Dict:
        """Get today's trading summary."""
        return {
            'date': str(self.today_stats.date),
            'trades': self.today_stats.trades,
            'wins': self.today_stats.wins,
            'losses': self.today_stats.losses,
            'win_rate': self.today_stats.wins / self.today_stats.trades if self.today_stats.trades > 0 else 0,
            'gross_pnl': self.today_stats.gross_pnl,
            'total_r': self.today_stats.total_r,
            'consecutive_losses': self.today_stats.consecutive_losses,
            'account_balance': self.account_balance,
            'daily_risk_used': abs(self.today_stats.gross_pnl) / self.account_balance if self.today_stats.gross_pnl < 0 else 0,
        }

    def reset_daily(self):
        """Reset for new trading day."""
        self.today_stats = DailyStats(date=date.today())
        self._save_state()


# Kelly Criterion Calculator
def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate Kelly Criterion for optimal position sizing.

    Formula: f* = (p * b - q) / b
    Where:
        p = probability of winning
        q = probability of losing (1 - p)
        b = ratio of win to loss

    We use HALF Kelly for safety.
    """
    if avg_loss == 0:
        return 0

    p = win_rate
    q = 1 - p
    b = avg_win / avg_loss

    kelly = (p * b - q) / b

    # Half Kelly for safety
    half_kelly = kelly / 2

    # Cap at 25% max
    return max(0, min(0.25, half_kelly))


# Test
if __name__ == "__main__":
    print("=" * 50)
    print("  RISK MANAGER TEST")
    print("=" * 50)

    rm = RiskManager(account_balance=10000)

    print(f"\nAccount: ${rm.account_balance:,.0f}")

    # Test trade approval
    decision = rm.can_take_trade(
        risk_per_share=1.50,
        entry_price=150.00,
    )

    print(f"\nCan trade: {decision.can_trade}")
    print(f"Status: {decision.status.value}")
    print(f"Max risk: ${decision.max_risk_dollars:.0f}")
    print(f"Position size: {decision.position_size_pct:.1%}")

    # Calculate position
    position = rm.calculate_position_size(
        entry_price=150.00,
        stop_price=148.50,
    )

    print(f"\nPosition calculation:")
    print(f"  Shares: {position['shares']}")
    print(f"  Dollar risk: ${position['dollar_risk']:.0f}")
    print(f"  Position value: ${position['position_value']:.0f}")

    # Test Kelly
    print(f"\nKelly Criterion:")
    print(f"  60% win rate, 2:1 R:R = {kelly_criterion(0.6, 2.0, 1.0):.1%}")
    print(f"  55% win rate, 1.5:1 R:R = {kelly_criterion(0.55, 1.5, 1.0):.1%}")
