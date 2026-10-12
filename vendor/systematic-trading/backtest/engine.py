"""
0DTE Trading System - Backtesting & Visualization Module
========================================================
Simulates historical trades using the same detection and confirmation rules.

Features:
  - Historical simulation with realistic fills
  - Performance metrics (win rate, R:R, drawdowns)
  - Visual overlays (zones, triggers, entries/exits)
  - Walk-forward optimization support

Output Metrics:
  - Win Rate
  - Average R:R
  - Profit Factor
  - Max Drawdown
  - Sharpe Ratio
  - Best/Worst Trade
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle


@dataclass
class BacktestTrade:
    """Single backtested trade."""
    entry_time: datetime
    exit_time: datetime
    symbol: str
    direction: str  # 'long' or 'short'

    entry_price: float
    exit_price: float
    stop_loss: float
    target_1: float

    shares: int
    pnl: float
    pnl_pct: float
    r_multiple: float

    exit_reason: str  # 'target', 'stop', 'trailing', 'eod'

    # Signal metadata
    zone_confidence: float = 0.0
    pattern_type: str = ""
    confluence_score: float = 0.0
    ml_probability: float = 0.0


@dataclass
class BacktestResult:
    """Complete backtest results."""
    trades: List[BacktestTrade]
    equity_curve: pd.Series
    daily_returns: pd.Series

    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0

    profit_factor: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0

    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_consecutive_losses: int = 0

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_trade_duration: float = 0.0  # minutes

    def __post_init__(self):
        """Calculate all metrics from trades."""
        if not self.trades:
            return

        self.total_trades = len(self.trades)
        self.winning_trades = len([t for t in self.trades if t.pnl > 0])
        self.losing_trades = len([t for t in self.trades if t.pnl <= 0])

        # Win rate
        self.win_rate = self.winning_trades / self.total_trades * 100 if self.total_trades > 0 else 0

        # Average win/loss
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        losses = [t.pnl for t in self.trades if t.pnl <= 0]

        self.avg_win = np.mean(wins) if wins else 0
        self.avg_loss = abs(np.mean(losses)) if losses else 0

        # Average R:R
        self.avg_rr = np.mean([t.r_multiple for t in self.trades])

        # Profit factor
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 1
        self.profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Total P&L
        self.total_pnl = sum(t.pnl for t in self.trades)
        self.total_pnl_pct = sum(t.pnl_pct for t in self.trades)

        # Best/Worst trade
        self.best_trade = max(t.pnl for t in self.trades)
        self.worst_trade = min(t.pnl for t in self.trades)

        # Average duration
        durations = [(t.exit_time - t.entry_time).seconds / 60 for t in self.trades]
        self.avg_trade_duration = np.mean(durations)

        # Consecutive losses
        max_losses = 0
        current_losses = 0
        for t in self.trades:
            if t.pnl <= 0:
                current_losses += 1
                max_losses = max(max_losses, current_losses)
            else:
                current_losses = 0
        self.max_consecutive_losses = max_losses

        # Drawdown from equity curve
        if len(self.equity_curve) > 0:
            running_max = self.equity_curve.expanding().max()
            drawdown = self.equity_curve - running_max
            self.max_drawdown = drawdown.min()
            self.max_drawdown_pct = (drawdown / running_max).min() * 100

        # Sharpe ratio (annualized)
        if len(self.daily_returns) > 1:
            daily_std = self.daily_returns.std()
            if daily_std > 0:
                self.sharpe_ratio = (self.daily_returns.mean() / daily_std) * np.sqrt(252)

            # Sortino (downside deviation)
            downside = self.daily_returns[self.daily_returns < 0]
            if len(downside) > 0:
                downside_std = downside.std()
                if downside_std > 0:
                    self.sortino_ratio = (self.daily_returns.mean() / downside_std) * np.sqrt(252)

            # Calmar ratio
            if self.max_drawdown_pct != 0:
                annual_return = self.daily_returns.mean() * 252
                self.calmar_ratio = annual_return / abs(self.max_drawdown_pct)

    def print_summary(self) -> None:
        """Print formatted backtest summary."""
        print("=" * 60)
        print("  BACKTEST RESULTS")
        print("=" * 60)
        print(f"\n  Total Trades: {self.total_trades}")
        print(f"  Wins: {self.winning_trades} | Losses: {self.losing_trades}")
        print(f"  Win Rate: {self.win_rate:.1f}%")
        print(f"\n  Average Win: ${self.avg_win:.2f}")
        print(f"  Average Loss: ${self.avg_loss:.2f}")
        print(f"  Average R:R: {self.avg_rr:.2f}")
        print(f"  Profit Factor: {self.profit_factor:.2f}")
        print(f"\n  Total P&L: ${self.total_pnl:.2f} ({self.total_pnl_pct:.1f}%)")
        print(f"  Best Trade: ${self.best_trade:.2f}")
        print(f"  Worst Trade: ${self.worst_trade:.2f}")
        print(f"\n  Max Drawdown: ${self.max_drawdown:.2f} ({self.max_drawdown_pct:.1f}%)")
        print(f"  Max Consecutive Losses: {self.max_consecutive_losses}")
        print(f"\n  Sharpe Ratio: {self.sharpe_ratio:.2f}")
        print(f"  Sortino Ratio: {self.sortino_ratio:.2f}")
        print(f"  Avg Trade Duration: {self.avg_trade_duration:.0f} min")
        print("=" * 60)


class BacktestEngine:
    """
    Backtesting engine for the 0DTE trading system.
    """

    def __init__(
        self,
        initial_capital: float = 25000.0,
        risk_per_trade: float = 0.02,
        slippage: float = 0.01,  # 1 cent slippage
        commission: float = 0.0,  # Per share commission
    ):
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.slippage = slippage
        self.commission = commission

        self.capital = initial_capital
        self.trades: List[BacktestTrade] = []
        self.equity_history: List[Tuple[datetime, float]] = []

    def run_backtest(
        self,
        df: pd.DataFrame,
        zones: List,  # List of Zone objects
        patterns: List,  # List of CandlePattern objects
        confluence_threshold: float = 50.0,
    ) -> BacktestResult:
        """
        Run backtest on historical data.

        Args:
            df: OHLCV DataFrame
            zones: Detected zones from ZoneDetector
            patterns: Detected patterns from CandlestickDetector
            confluence_threshold: Minimum confluence score to trade

        Returns:
            BacktestResult object
        """
        self.capital = self.initial_capital
        self.trades = []
        self.equity_history = [(df.index[0], self.capital)]

        active_position = None

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i - 1]
            timestamp = df.index[i]

            # Update equity history
            if active_position:
                # Check exits
                exit_info = self._check_exit(active_position, row)
                if exit_info:
                    self._close_position(active_position, exit_info, timestamp)
                    active_position = None

            # Look for new entries (only if no active position)
            if not active_position:
                signal = self._check_entry(df.iloc[:i+1], zones, patterns, confluence_threshold)
                if signal:
                    active_position = self._open_position(signal, row, timestamp)

            # Record equity
            current_equity = self._calculate_equity(active_position, row['close'])
            self.equity_history.append((timestamp, current_equity))

        # Close any remaining position at end
        if active_position:
            self._close_position(active_position, {'reason': 'eod', 'price': df.iloc[-1]['close']}, df.index[-1])

        # Build result
        equity_df = pd.DataFrame(self.equity_history, columns=['time', 'equity']).set_index('time')
        daily_returns = equity_df['equity'].pct_change().dropna()

        return BacktestResult(
            trades=self.trades,
            equity_curve=equity_df['equity'],
            daily_returns=daily_returns,
        )

    def _check_entry(
        self,
        df: pd.DataFrame,
        zones: List,
        patterns: List,
        threshold: float,
    ) -> Optional[Dict]:
        """Check for entry signal at current bar."""
        current_price = df.iloc[-1]['close']
        current_time = df.index[-1]

        # Find zones near current price
        for zone in zones:
            if not zone.is_valid:
                continue

            # Check if price is in zone
            if not zone.contains_price(current_price):
                continue

            # Check for confirming pattern
            recent_patterns = [p for p in patterns
                              if p.bar_index >= len(df) - 3]

            for pattern in recent_patterns:
                # Match direction
                if zone.zone_type.value == 'demand' and pattern.direction.value != 'bullish':
                    continue
                if zone.zone_type.value == 'supply' and pattern.direction.value != 'bearish':
                    continue

                # Check confluence
                confluence = (zone.confidence_score + pattern.strength) / 2
                if confluence >= threshold:
                    return {
                        'zone': zone,
                        'pattern': pattern,
                        'confluence': confluence,
                        'direction': 'long' if zone.zone_type.value == 'demand' else 'short',
                        'entry_price': zone.midpoint,
                        'stop_loss': zone.lower if zone.zone_type.value == 'demand' else zone.upper,
                    }

        return None

    def _open_position(self, signal: Dict, row: pd.Series, timestamp: datetime) -> Dict:
        """Open a new position."""
        direction = signal['direction']
        entry_price = signal['entry_price'] + (self.slippage if direction == 'long' else -self.slippage)
        stop_loss = signal['stop_loss']

        # Calculate risk and position size
        risk_per_share = abs(entry_price - stop_loss)
        risk_amount = self.capital * self.risk_per_trade
        shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

        # Calculate targets
        if direction == 'long':
            target_1 = entry_price + risk_per_share  # 1R
            target_2 = entry_price + risk_per_share * 2  # 2R
        else:
            target_1 = entry_price - risk_per_share
            target_2 = entry_price - risk_per_share * 2

        return {
            'entry_time': timestamp,
            'direction': direction,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'target_1': target_1,
            'target_2': target_2,
            'shares': shares,
            'risk_per_share': risk_per_share,
            'zone': signal['zone'],
            'pattern': signal['pattern'],
            'confluence': signal['confluence'],
        }

    def _check_exit(self, position: Dict, row: pd.Series) -> Optional[Dict]:
        """Check if position should exit."""
        direction = position['direction']
        high = row['high']
        low = row['low']

        if direction == 'long':
            # Check stop
            if low <= position['stop_loss']:
                return {'reason': 'stop', 'price': position['stop_loss'] - self.slippage}
            # Check target
            if high >= position['target_1']:
                return {'reason': 'target', 'price': position['target_1'] - self.slippage}
        else:
            # Check stop
            if high >= position['stop_loss']:
                return {'reason': 'stop', 'price': position['stop_loss'] + self.slippage}
            # Check target
            if low <= position['target_1']:
                return {'reason': 'target', 'price': position['target_1'] + self.slippage}

        return None

    def _close_position(self, position: Dict, exit_info: Dict, timestamp: datetime) -> None:
        """Close position and record trade."""
        exit_price = exit_info['price']
        shares = position['shares']

        # Calculate P&L
        if position['direction'] == 'long':
            pnl = (exit_price - position['entry_price']) * shares
        else:
            pnl = (position['entry_price'] - exit_price) * shares

        # Commission
        pnl -= self.commission * shares * 2  # Entry + exit

        # R-multiple
        r_multiple = pnl / (position['risk_per_share'] * shares) if position['risk_per_share'] > 0 else 0

        # Update capital
        self.capital += pnl

        # Record trade
        trade = BacktestTrade(
            entry_time=position['entry_time'],
            exit_time=timestamp,
            symbol='BACKTEST',
            direction=position['direction'],
            entry_price=position['entry_price'],
            exit_price=exit_price,
            stop_loss=position['stop_loss'],
            target_1=position['target_1'],
            shares=shares,
            pnl=pnl,
            pnl_pct=pnl / self.initial_capital * 100,
            r_multiple=r_multiple,
            exit_reason=exit_info['reason'],
            zone_confidence=position['zone'].confidence_score,
            pattern_type=position['pattern'].pattern_type.value,
            confluence_score=position['confluence'],
        )

        self.trades.append(trade)

    def _calculate_equity(self, position: Optional[Dict], current_price: float) -> float:
        """Calculate current equity including unrealized P&L."""
        if not position:
            return self.capital

        if position['direction'] == 'long':
            unrealized = (current_price - position['entry_price']) * position['shares']
        else:
            unrealized = (position['entry_price'] - current_price) * position['shares']

        return self.capital + unrealized


class Visualizer:
    """
    Creates trading charts and visualizations.
    """

    @staticmethod
    def plot_backtest(
        df: pd.DataFrame,
        result: BacktestResult,
        zones: List = None,
        title: str = "Backtest Results",
        save_path: Optional[str] = None,
    ) -> None:
        """
        Plot backtest results with price, zones, and trades.
        """
        fig, axes = plt.subplots(3, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1, 1]})

        # Price chart with zones and trades
        ax1 = axes[0]
        ax1.plot(df.index, df['close'], 'b-', linewidth=1, label='Price')

        # Plot zones
        if zones:
            for zone in zones[:20]:  # Limit zones shown
                color = 'green' if zone.zone_type.value == 'demand' else 'red'
                alpha = 0.3 if zone.is_valid else 0.1
                rect = Rectangle(
                    (mdates.date2num(zone.formation_time), zone.lower),
                    mdates.date2num(df.index[-1]) - mdates.date2num(zone.formation_time),
                    zone.height,
                    facecolor=color,
                    alpha=alpha,
                    edgecolor=color,
                    linewidth=1,
                )
                ax1.add_patch(rect)

        # Plot trades
        for trade in result.trades:
            color = 'green' if trade.pnl > 0 else 'red'
            marker = '^' if trade.direction == 'long' else 'v'

            # Entry
            ax1.scatter(trade.entry_time, trade.entry_price, marker=marker,
                       color='blue', s=100, zorder=5)
            # Exit
            ax1.scatter(trade.exit_time, trade.exit_price, marker='o',
                       color=color, s=100, zorder=5)
            # Connect
            ax1.plot([trade.entry_time, trade.exit_time],
                    [trade.entry_price, trade.exit_price],
                    color=color, linestyle='--', alpha=0.5)

        ax1.set_ylabel('Price')
        ax1.set_title(title)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Equity curve
        ax2 = axes[1]
        ax2.plot(result.equity_curve.index, result.equity_curve.values, 'g-', linewidth=1.5)
        ax2.fill_between(result.equity_curve.index, result.equity_curve.values.min(),
                        result.equity_curve.values, alpha=0.3, color='green')
        ax2.set_ylabel('Equity ($)')
        ax2.grid(True, alpha=0.3)

        # Trade P&L
        ax3 = axes[2]
        pnls = [t.pnl for t in result.trades]
        colors = ['green' if p > 0 else 'red' for p in pnls]
        ax3.bar(range(len(pnls)), pnls, color=colors, alpha=0.7)
        ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax3.set_xlabel('Trade #')
        ax3.set_ylabel('P&L ($)')
        ax3.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.show()

    @staticmethod
    def plot_metrics(result: BacktestResult, save_path: Optional[str] = None) -> None:
        """Plot performance metrics dashboard."""
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))

        # Win/Loss distribution
        ax1 = axes[0, 0]
        wins = [t.pnl for t in result.trades if t.pnl > 0]
        losses = [t.pnl for t in result.trades if t.pnl <= 0]
        ax1.hist([wins, losses], bins=20, label=['Wins', 'Losses'], color=['green', 'red'], alpha=0.7)
        ax1.axvline(x=0, color='black', linestyle='--')
        ax1.set_xlabel('P&L ($)')
        ax1.set_ylabel('Frequency')
        ax1.set_title('P&L Distribution')
        ax1.legend()

        # R-Multiple distribution
        ax2 = axes[0, 1]
        r_mults = [t.r_multiple for t in result.trades]
        ax2.hist(r_mults, bins=20, color='blue', alpha=0.7, edgecolor='black')
        ax2.axvline(x=0, color='red', linestyle='--')
        ax2.axvline(x=np.mean(r_mults), color='green', linestyle='--', label=f'Mean: {np.mean(r_mults):.2f}R')
        ax2.set_xlabel('R-Multiple')
        ax2.set_ylabel('Frequency')
        ax2.set_title('R-Multiple Distribution')
        ax2.legend()

        # Cumulative P&L
        ax3 = axes[1, 0]
        cum_pnl = np.cumsum([t.pnl for t in result.trades])
        ax3.plot(cum_pnl, 'b-', linewidth=1.5)
        ax3.fill_between(range(len(cum_pnl)), 0, cum_pnl,
                        where=cum_pnl >= 0, alpha=0.3, color='green')
        ax3.fill_between(range(len(cum_pnl)), 0, cum_pnl,
                        where=cum_pnl < 0, alpha=0.3, color='red')
        ax3.set_xlabel('Trade #')
        ax3.set_ylabel('Cumulative P&L ($)')
        ax3.set_title('Cumulative P&L')
        ax3.grid(True, alpha=0.3)

        # Win rate by confluence
        ax4 = axes[1, 1]
        conf_bins = [40, 50, 60, 70, 80, 90, 100]
        win_rates = []
        for i in range(len(conf_bins) - 1):
            trades_in_bin = [t for t in result.trades
                           if conf_bins[i] <= t.confluence_score < conf_bins[i+1]]
            if trades_in_bin:
                wr = len([t for t in trades_in_bin if t.pnl > 0]) / len(trades_in_bin) * 100
            else:
                wr = 0
            win_rates.append(wr)

        x_labels = [f'{conf_bins[i]}-{conf_bins[i+1]}' for i in range(len(conf_bins)-1)]
        ax4.bar(x_labels, win_rates, color='blue', alpha=0.7, edgecolor='black')
        ax4.axhline(y=50, color='red', linestyle='--', label='50%')
        ax4.set_xlabel('Confluence Score')
        ax4.set_ylabel('Win Rate (%)')
        ax4.set_title('Win Rate by Confluence')
        ax4.legend()

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.show()


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    import sys
    import os; sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data.fetcher import DataFetcher
    from zones.detector import ZoneDetector
    from signals.candlestick import CandlestickDetector

    print("=== BACKTEST ENGINE TEST ===\n")

    # Fetch data
    fetcher = DataFetcher()
    data = fetcher.fetch_market_data('QQQ', '5m', '1mo')

    # Detect zones and patterns
    zone_detector = ZoneDetector()
    zones = zone_detector.detect_zones(data.ohlcv)

    candle_detector = CandlestickDetector()
    patterns = candle_detector.detect_patterns(data.ohlcv)

    print(f"Data points: {len(data.ohlcv)}")
    print(f"Zones detected: {len(zones)}")
    print(f"Patterns detected: {len(patterns)}")

    # Run backtest
    engine = BacktestEngine(
        initial_capital=25000,
        risk_per_trade=0.02,
        slippage=0.02,
    )

    result = engine.run_backtest(
        df=data.ohlcv,
        zones=zones,
        patterns=patterns,
        confluence_threshold=55,
    )

    # Print results
    result.print_summary()

    # Visualize (if in interactive environment)
    try:
        Visualizer.plot_backtest(data.ohlcv, result, zones, title="QQQ 0DTE Backtest")
        Visualizer.plot_metrics(result)
    except Exception as e:
        print(f"\nVisualization skipped: {e}")
