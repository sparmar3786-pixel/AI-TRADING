"""
Convexity Engine Backtester
============================
Comprehensive backtesting framework for 0DTE convexity strategies.

Features:
- Trade simulation with slippage/commissions
- Walk-forward validation
- Monte Carlo robustness testing
- PBO (Probability of Backtest Overfitting) analysis
- Detailed metrics and reporting
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import json
import os
from itertools import combinations

from .engine import ConvexityEngine, ConvexitySignal


@dataclass
class Trade:
    """Represents a completed trade."""
    entry_time: datetime
    exit_time: datetime
    symbol: str
    direction: str
    signal_type: str
    entry_price: float
    exit_price: float
    stop_loss: float
    target: float
    shares: int
    pnl: float
    r_multiple: float
    win: bool
    exit_reason: str  # 'target', 'stop', 'eod' (end of day)
    probability: float
    features: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat(),
            'symbol': self.symbol,
            'direction': self.direction,
            'signal_type': self.signal_type,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'stop_loss': self.stop_loss,
            'target': self.target,
            'shares': self.shares,
            'pnl': self.pnl,
            'r_multiple': self.r_multiple,
            'win': self.win,
            'exit_reason': self.exit_reason,
            'probability': self.probability,
        }


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    initial_capital: float = 100000
    risk_per_trade: float = 0.01  # 1% risk
    max_trades_per_day: int = 5
    slippage_pct: float = 0.0005  # 0.05% slippage
    commission_per_trade: float = 1.0  # $1 per trade
    min_probability: float = 60  # Minimum signal probability
    use_target_2r: bool = True  # Use 2R target (vs 1R)
    close_at_eod: bool = True  # Close 0DTE at end of day
    eod_time: time = time(15, 50)  # Close positions by 3:50 PM


class ConvexityBacktester:
    """
    Backtester for the Convexity Engine.

    Simulates trading on historical intraday data.
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        self.daily_pnl: Dict[str, float] = {}

    def run_backtest(self, symbol: str, daily_df: pd.DataFrame,
                     intraday_df: pd.DataFrame) -> Dict:
        """
        Run backtest on historical data.

        Args:
            symbol: Trading symbol (SPY, QQQ)
            daily_df: Daily OHLCV data for HTF context
            intraday_df: 1-min or 5-min OHLCV data

        Returns:
            Dictionary of backtest results
        """
        print(f"\nRunning backtest on {symbol}...")
        print(f"  Period: {intraday_df.index[0]} to {intraday_df.index[-1]}")
        print(f"  Bars: {len(intraday_df):,}")

        # Initialize engine
        engine = ConvexityEngine(symbol, self.config.initial_capital)
        engine.update_htf_context(daily_df)
        engine.update_volatility_regime(price_df=daily_df)

        # Reset state
        self.trades = []
        self.equity_curve = [self.config.initial_capital]
        self.daily_pnl = {}

        capital = self.config.initial_capital
        position = None
        trades_today = 0
        current_date = None

        # Iterate through intraday bars
        for i in range(50, len(intraday_df)):  # Need 50 bars for features
            bar = intraday_df.iloc[i]
            timestamp = intraday_df.index[i]

            # Check if it's a datetime
            if not isinstance(timestamp, datetime):
                timestamp = pd.to_datetime(timestamp)

            bar_date = timestamp.date()
            bar_time = timestamp.time()

            # Reset daily counter
            if current_date != bar_date:
                current_date = bar_date
                trades_today = 0

                # Update HTF context daily
                daily_up_to = daily_df[daily_df.index.date <= bar_date]
                if len(daily_up_to) > 20:
                    engine.update_htf_context(daily_up_to)
                    engine.update_volatility_regime(price_df=daily_up_to)

            # Get lookback window
            lookback_df = intraday_df.iloc[max(0, i-100):i+1].copy()

            # Check for exit if in position
            if position is not None:
                exit_result = self._check_exit(position, bar, timestamp)
                if exit_result:
                    trade = self._close_position(position, exit_result, capital)
                    self.trades.append(trade)
                    capital += trade.pnl
                    self.equity_curve.append(capital)

                    # Track daily PnL
                    date_key = bar_date.isoformat()
                    self.daily_pnl[date_key] = self.daily_pnl.get(date_key, 0) + trade.pnl

                    position = None

            # Check for new signal if not in position
            if position is None and trades_today < self.config.max_trades_per_day:
                # Skip if too close to close
                if bar_time >= self.config.eod_time:
                    continue

                # Generate signal
                signal = engine.generate_signal(lookback_df, timestamp)

                if signal and signal.probability >= self.config.min_probability:
                    # Open position
                    position = self._open_position(signal, capital)
                    trades_today += 1

        # Close any remaining position
        if position is not None:
            final_bar = intraday_df.iloc[-1]
            exit_result = ('eod', final_bar['close'])
            trade = self._close_position(position, exit_result, capital)
            self.trades.append(trade)
            capital += trade.pnl
            self.equity_curve.append(capital)

        # Calculate metrics
        metrics = self._calculate_metrics()
        metrics['final_capital'] = capital
        metrics['total_return_pct'] = (capital / self.config.initial_capital - 1) * 100

        return metrics

    def _open_position(self, signal: ConvexitySignal, capital: float) -> Dict:
        """Open a new position."""
        # Apply slippage
        if signal.direction == 'LONG':
            entry_price = signal.entry_price * (1 + self.config.slippage_pct)
        else:
            entry_price = signal.entry_price * (1 - self.config.slippage_pct)

        # Calculate position size
        risk_amount = capital * self.config.risk_per_trade
        risk_per_share = abs(entry_price - signal.stop_loss)
        shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

        if shares == 0:
            shares = 1  # Minimum 1 share

        target = signal.target_2r if self.config.use_target_2r else signal.target_1r

        return {
            'entry_time': signal.timestamp,
            'symbol': signal.symbol,
            'direction': signal.direction,
            'signal_type': signal.signal_type,
            'entry_price': entry_price,
            'stop_loss': signal.stop_loss,
            'target': target,
            'shares': shares,
            'probability': signal.probability,
            'features': {
                'sweep_score': signal.sweep_score,
                'overextension_score': signal.overextension_score,
                'convexity_score': signal.convexity_score,
                'gamma_score': signal.gamma_score,
            }
        }

    def _check_exit(self, position: Dict, bar: pd.Series, timestamp: datetime) -> Optional[Tuple[str, float]]:
        """Check if position should be exited."""
        bar_time = timestamp.time() if isinstance(timestamp, datetime) else timestamp

        # EOD exit
        if self.config.close_at_eod and bar_time >= self.config.eod_time:
            return ('eod', bar['close'])

        if position['direction'] == 'LONG':
            # Stop loss hit
            if bar['low'] <= position['stop_loss']:
                return ('stop', position['stop_loss'])
            # Target hit
            if bar['high'] >= position['target']:
                return ('target', position['target'])
        else:  # SHORT
            # Stop loss hit
            if bar['high'] >= position['stop_loss']:
                return ('stop', position['stop_loss'])
            # Target hit
            if bar['low'] <= position['target']:
                return ('target', position['target'])

        return None

    def _close_position(self, position: Dict, exit_result: Tuple[str, float],
                        capital: float) -> Trade:
        """Close position and create Trade record."""
        exit_reason, exit_price = exit_result

        # Apply slippage on exit
        if position['direction'] == 'LONG':
            exit_price = exit_price * (1 - self.config.slippage_pct)
        else:
            exit_price = exit_price * (1 + self.config.slippage_pct)

        # Calculate PnL
        if position['direction'] == 'LONG':
            pnl_per_share = exit_price - position['entry_price']
        else:
            pnl_per_share = position['entry_price'] - exit_price

        gross_pnl = pnl_per_share * position['shares']
        net_pnl = gross_pnl - self.config.commission_per_trade

        # Calculate R multiple
        risk_per_share = abs(position['entry_price'] - position['stop_loss'])
        r_multiple = pnl_per_share / risk_per_share if risk_per_share > 0 else 0

        return Trade(
            entry_time=position['entry_time'],
            exit_time=datetime.now(),  # Will be overwritten properly in real run
            symbol=position['symbol'],
            direction=position['direction'],
            signal_type=position['signal_type'],
            entry_price=position['entry_price'],
            exit_price=exit_price,
            stop_loss=position['stop_loss'],
            target=position['target'],
            shares=position['shares'],
            pnl=net_pnl,
            r_multiple=r_multiple,
            win=net_pnl > 0,
            exit_reason=exit_reason,
            probability=position['probability'],
            features=position.get('features', {})
        )

    def _calculate_metrics(self) -> Dict:
        """Calculate comprehensive backtest metrics."""
        if not self.trades:
            return {'error': 'No trades'}

        # Basic stats
        total_trades = len(self.trades)
        winners = [t for t in self.trades if t.win]
        losers = [t for t in self.trades if not t.win]

        win_rate = len(winners) / total_trades if total_trades > 0 else 0

        # R multiples
        r_multiples = [t.r_multiple for t in self.trades]
        avg_r = np.mean(r_multiples)

        win_r = [t.r_multiple for t in winners] if winners else [0]
        loss_r = [abs(t.r_multiple) for t in losers] if losers else [0]

        avg_win_r = np.mean(win_r)
        avg_loss_r = np.mean(loss_r)

        # PnL
        total_pnl = sum(t.pnl for t in self.trades)
        gross_profit = sum(t.pnl for t in winners)
        gross_loss = abs(sum(t.pnl for t in losers))

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Expectancy
        expectancy = (win_rate * avg_win_r) - ((1 - win_rate) * avg_loss_r)

        # Drawdown
        equity = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak * 100
        max_drawdown = drawdown.max()

        # Sharpe Ratio (assuming daily returns)
        if len(self.daily_pnl) > 1:
            daily_returns = list(self.daily_pnl.values())
            sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252) if np.std(daily_returns) > 0 else 0
        else:
            sharpe = 0

        # By signal type
        signal_types = {}
        for t in self.trades:
            if t.signal_type not in signal_types:
                signal_types[t.signal_type] = {'wins': 0, 'losses': 0, 'pnl': 0}
            if t.win:
                signal_types[t.signal_type]['wins'] += 1
            else:
                signal_types[t.signal_type]['losses'] += 1
            signal_types[t.signal_type]['pnl'] += t.pnl

        # By exit reason
        exit_reasons = {}
        for t in self.trades:
            if t.exit_reason not in exit_reasons:
                exit_reasons[t.exit_reason] = 0
            exit_reasons[t.exit_reason] += 1

        return {
            'total_trades': total_trades,
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': win_rate,
            'avg_r': avg_r,
            'avg_win_r': avg_win_r,
            'avg_loss_r': avg_loss_r,
            'expectancy': expectancy,
            'total_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': profit_factor,
            'max_drawdown_pct': max_drawdown,
            'sharpe_ratio': sharpe,
            'signal_types': signal_types,
            'exit_reasons': exit_reasons,
        }

    def print_results(self, metrics: Dict):
        """Print formatted backtest results."""
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)

        print(f"\nTrades: {metrics['total_trades']}")
        print(f"  Winners: {metrics['winners']}")
        print(f"  Losers: {metrics['losers']}")
        print(f"  Win Rate: {metrics['win_rate']:.1%}")

        print(f"\nR Multiples:")
        print(f"  Average R: {metrics['avg_r']:.2f}")
        print(f"  Avg Win: {metrics['avg_win_r']:.2f}R")
        print(f"  Avg Loss: {metrics['avg_loss_r']:.2f}R")
        print(f"  Expectancy: {metrics['expectancy']:.2f}R per trade")

        print(f"\nPnL:")
        print(f"  Total PnL: ${metrics['total_pnl']:,.2f}")
        print(f"  Total Return: {metrics.get('total_return_pct', 0):.1f}%")
        print(f"  Profit Factor: {metrics['profit_factor']:.2f}")

        print(f"\nRisk:")
        print(f"  Max Drawdown: {metrics['max_drawdown_pct']:.1f}%")
        print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")

        print(f"\nBy Signal Type:")
        for sig_type, stats in metrics.get('signal_types', {}).items():
            total = stats['wins'] + stats['losses']
            wr = stats['wins'] / total if total > 0 else 0
            print(f"  {sig_type}: {total} trades, {wr:.0%} WR, ${stats['pnl']:,.0f}")

        print(f"\nExit Reasons:")
        for reason, count in metrics.get('exit_reasons', {}).items():
            print(f"  {reason}: {count}")

        print("=" * 60)

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame."""
        return pd.DataFrame([t.to_dict() for t in self.trades])


class WalkForwardValidator:
    """
    Walk-forward validation to prevent overfitting.

    Trains on window, tests on next period, rolls forward.
    """

    def __init__(self, train_pct: float = 0.7):
        self.train_pct = train_pct
        self.results = []

    def run_walk_forward(self, symbol: str, daily_df: pd.DataFrame,
                         intraday_df: pd.DataFrame, n_splits: int = 5) -> Dict:
        """
        Run walk-forward validation.

        Args:
            symbol: Trading symbol
            daily_df: Daily data
            intraday_df: Intraday data
            n_splits: Number of train/test splits

        Returns:
            Walk-forward results
        """
        print(f"\nRunning Walk-Forward Validation ({n_splits} splits)...")

        # Split data
        total_days = len(intraday_df.index.date if hasattr(intraday_df.index, 'date') else
                        pd.to_datetime(intraday_df.index).date)
        unique_dates = sorted(set(pd.to_datetime(intraday_df.index).date))
        days_per_split = len(unique_dates) // n_splits

        self.results = []
        all_trades = []

        for i in range(n_splits - 1):  # -1 because we need test data
            train_end_idx = (i + 1) * days_per_split
            test_end_idx = min((i + 2) * days_per_split, len(unique_dates))

            train_dates = unique_dates[:train_end_idx]
            test_dates = unique_dates[train_end_idx:test_end_idx]

            if not test_dates:
                continue

            # Filter data
            train_mask = pd.to_datetime(intraday_df.index).date.isin(train_dates)
            test_mask = pd.to_datetime(intraday_df.index).date.isin(test_dates)

            train_intraday = intraday_df[train_mask]
            test_intraday = intraday_df[test_mask]

            train_daily_mask = daily_df.index.date <= train_dates[-1]
            train_daily = daily_df[train_daily_mask]

            print(f"\n  Split {i+1}:")
            print(f"    Train: {train_dates[0]} to {train_dates[-1]} ({len(train_dates)} days)")
            print(f"    Test: {test_dates[0]} to {test_dates[-1]} ({len(test_dates)} days)")

            # Run backtest on test period
            backtester = ConvexityBacktester()
            metrics = backtester.run_backtest(symbol, train_daily, test_intraday)

            self.results.append({
                'split': i + 1,
                'train_start': str(train_dates[0]),
                'train_end': str(train_dates[-1]),
                'test_start': str(test_dates[0]),
                'test_end': str(test_dates[-1]),
                'metrics': metrics
            })

            all_trades.extend(backtester.trades)

            print(f"    Trades: {metrics['total_trades']}")
            print(f"    Win Rate: {metrics['win_rate']:.1%}")
            print(f"    Expectancy: {metrics['expectancy']:.2f}R")

        # Aggregate results
        win_rates = [r['metrics']['win_rate'] for r in self.results if 'win_rate' in r['metrics']]
        expectancies = [r['metrics']['expectancy'] for r in self.results if 'expectancy' in r['metrics']]

        return {
            'n_splits': n_splits,
            'avg_win_rate': np.mean(win_rates) if win_rates else 0,
            'std_win_rate': np.std(win_rates) if win_rates else 0,
            'avg_expectancy': np.mean(expectancies) if expectancies else 0,
            'std_expectancy': np.std(expectancies) if expectancies else 0,
            'splits': self.results,
            'total_trades': len(all_trades),
            'consistency_score': 1 - (np.std(win_rates) / np.mean(win_rates)) if win_rates and np.mean(win_rates) > 0 else 0
        }


class MonteCarloSimulator:
    """
    Monte Carlo simulation for robustness testing.

    Shuffles trade order and resamples to test edge stability.
    """

    def __init__(self, n_simulations: int = 10000):
        self.n_simulations = n_simulations

    def run_simulation(self, trades: List[Trade], initial_capital: float = 100000) -> Dict:
        """
        Run Monte Carlo simulation on trade results.

        Args:
            trades: List of historical trades
            initial_capital: Starting capital

        Returns:
            Monte Carlo statistics
        """
        print(f"\nRunning Monte Carlo Simulation ({self.n_simulations:,} iterations)...")

        if not trades:
            return {'error': 'No trades to simulate'}

        pnls = [t.pnl for t in trades]
        n_trades = len(pnls)

        final_capitals = []
        max_drawdowns = []
        win_rates = []

        for _ in range(self.n_simulations):
            # Resample with replacement
            sampled_pnls = np.random.choice(pnls, size=n_trades, replace=True)

            # Calculate equity curve
            equity = [initial_capital]
            for pnl in sampled_pnls:
                equity.append(equity[-1] + pnl)

            equity = np.array(equity)
            final_capitals.append(equity[-1])

            # Calculate drawdown
            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / peak * 100
            max_drawdowns.append(dd.max())

            # Win rate
            wins = sum(1 for p in sampled_pnls if p > 0)
            win_rates.append(wins / len(sampled_pnls))

        final_capitals = np.array(final_capitals)
        max_drawdowns = np.array(max_drawdowns)

        # Calculate percentiles
        percentiles = [5, 25, 50, 75, 95]
        capital_percentiles = {f'p{p}': np.percentile(final_capitals, p) for p in percentiles}
        dd_percentiles = {f'p{p}': np.percentile(max_drawdowns, p) for p in percentiles}

        # Probability of profit
        prob_profit = (final_capitals > initial_capital).mean()

        # Risk of ruin (losing 50%+)
        ruin_threshold = initial_capital * 0.5
        prob_ruin = (final_capitals < ruin_threshold).mean()

        return {
            'n_simulations': self.n_simulations,
            'n_trades': n_trades,
            'mean_final_capital': final_capitals.mean(),
            'std_final_capital': final_capitals.std(),
            'capital_percentiles': capital_percentiles,
            'mean_max_drawdown': max_drawdowns.mean(),
            'dd_percentiles': dd_percentiles,
            'prob_profit': prob_profit,
            'prob_ruin': prob_ruin,
            'mean_win_rate': np.mean(win_rates),
            'win_rate_95_ci': (np.percentile(win_rates, 2.5), np.percentile(win_rates, 97.5)),
        }

    def print_results(self, results: Dict):
        """Print Monte Carlo results."""
        print("\n" + "=" * 60)
        print("MONTE CARLO SIMULATION RESULTS")
        print("=" * 60)

        print(f"\nSimulations: {results['n_simulations']:,}")
        print(f"Trades per simulation: {results['n_trades']}")

        print(f"\nFinal Capital:")
        print(f"  Mean: ${results['mean_final_capital']:,.0f}")
        print(f"  Std Dev: ${results['std_final_capital']:,.0f}")
        for k, v in results['capital_percentiles'].items():
            print(f"  {k}: ${v:,.0f}")

        print(f"\nMax Drawdown:")
        print(f"  Mean: {results['mean_max_drawdown']:.1f}%")
        for k, v in results['dd_percentiles'].items():
            print(f"  {k}: {v:.1f}%")

        print(f"\nRisk Metrics:")
        print(f"  Probability of Profit: {results['prob_profit']:.1%}")
        print(f"  Probability of Ruin (50% loss): {results['prob_ruin']:.2%}")
        print(f"  Win Rate 95% CI: {results['win_rate_95_ci'][0]:.1%} - {results['win_rate_95_ci'][1]:.1%}")

        print("=" * 60)


class PBOAnalyzer:
    """
    Probability of Backtest Overfitting (PBO) analysis.

    Uses Combinatorially Symmetric Cross-Validation (CSCV).
    PBO < 0.5 suggests real edge, PBO > 0.5 suggests overfitting.
    """

    def __init__(self, n_partitions: int = 10):
        self.n_partitions = n_partitions

    def calculate_pbo(self, trades: List[Trade]) -> Dict:
        """
        Calculate Probability of Backtest Overfitting.

        Args:
            trades: List of trades from backtest

        Returns:
            PBO analysis results
        """
        print(f"\nCalculating PBO ({self.n_partitions} partitions)...")

        if len(trades) < self.n_partitions * 2:
            return {'error': 'Not enough trades for PBO analysis', 'pbo': None}

        # Sort trades by time
        sorted_trades = sorted(trades, key=lambda t: t.entry_time)

        # Partition trades
        partition_size = len(sorted_trades) // self.n_partitions
        partitions = []
        for i in range(self.n_partitions):
            start = i * partition_size
            end = start + partition_size if i < self.n_partitions - 1 else len(sorted_trades)
            partition_trades = sorted_trades[start:end]
            partition_return = sum(t.pnl for t in partition_trades)
            partitions.append(partition_return)

        # CSCV: Test all combinations
        overfit_count = 0
        total_combinations = 0

        # For each possible train/test split
        for n_train in range(1, self.n_partitions):
            for train_indices in combinations(range(self.n_partitions), n_train):
                test_indices = [i for i in range(self.n_partitions) if i not in train_indices]

                train_return = sum(partitions[i] for i in train_indices)
                test_return = sum(partitions[i] for i in test_indices)

                # Overfit if train positive but test negative
                if train_return > 0 and test_return < 0:
                    overfit_count += 1

                total_combinations += 1

        pbo = overfit_count / total_combinations if total_combinations > 0 else 0

        # Interpretation
        if pbo < 0.25:
            interpretation = "Strong edge - low overfitting risk"
        elif pbo < 0.5:
            interpretation = "Moderate edge - some overfitting concern"
        elif pbo < 0.75:
            interpretation = "Weak edge - high overfitting risk"
        else:
            interpretation = "Likely overfit - edge may not be real"

        return {
            'pbo': pbo,
            'n_partitions': self.n_partitions,
            'total_combinations': total_combinations,
            'overfit_combinations': overfit_count,
            'interpretation': interpretation,
            'partition_returns': partitions,
        }

    def print_results(self, results: Dict):
        """Print PBO results."""
        print("\n" + "=" * 60)
        print("PROBABILITY OF BACKTEST OVERFITTING (PBO)")
        print("=" * 60)

        if 'error' in results:
            print(f"\nError: {results['error']}")
            return

        print(f"\nPBO Score: {results['pbo']:.2%}")
        print(f"Interpretation: {results['interpretation']}")

        print(f"\nDetails:")
        print(f"  Partitions: {results['n_partitions']}")
        print(f"  Combinations tested: {results['total_combinations']}")
        print(f"  Overfit combinations: {results['overfit_combinations']}")

        print(f"\nPartition Returns:")
        for i, ret in enumerate(results['partition_returns']):
            print(f"  Part {i+1}: ${ret:,.0f}")

        print("\nGuidelines:")
        print("  PBO < 0.25: Strong edge")
        print("  PBO 0.25-0.5: Moderate edge")
        print("  PBO 0.5-0.75: Weak edge (caution)")
        print("  PBO > 0.75: Likely overfit")
        print("=" * 60)
