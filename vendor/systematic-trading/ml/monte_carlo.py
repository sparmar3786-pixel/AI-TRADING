"""
Enhanced Monte Carlo Simulation
================================
Advanced Monte Carlo simulation with:
1. Timeframe-specific win rates (daily 96% vs hourly 65%)
2. Regime-aware win rate adjustments
3. Drawdown-sensitive position sizing
4. Kelly criterion integration
5. Confidence intervals and visualization

Stress-tests the discovered edges under various market conditions.

"The goal is not to predict the future, but to be prepared for it."
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class TimeframeEdge:
    """Edge characteristics for a specific timeframe."""
    timeframe: str  # 'daily', 'hourly', '5m'
    win_rate: float  # Base win rate (e.g., 0.96 for daily)
    avg_win_r: float  # Average win in R-multiples
    avg_loss_r: float  # Average loss in R-multiples
    sample_size: int  # Number of training samples
    confidence_interval: Tuple[float, float] = field(default=(0.0, 1.0))  # 95% CI on win rate

    def __post_init__(self):
        # Calculate CI if not provided
        if self.confidence_interval == (0.0, 1.0) and self.sample_size > 0:
            self.confidence_interval = wilson_confidence_interval(
                int(self.win_rate * self.sample_size),
                self.sample_size,
            )

    @property
    def expected_r(self) -> float:
        """Expected R per trade."""
        return (self.win_rate * self.avg_win_r) - ((1 - self.win_rate) * self.avg_loss_r)

    @property
    def kelly_fraction(self) -> float:
        """Optimal Kelly fraction."""
        return kelly_criterion(self.win_rate, self.avg_win_r, self.avg_loss_r)

    def __str__(self):
        return f"""
{self.timeframe.upper()} Edge
==================
Win Rate: {self.win_rate:.1%} (95% CI: {self.confidence_interval[0]:.1%} - {self.confidence_interval[1]:.1%})
Avg Win: {self.avg_win_r:.2f}R | Avg Loss: {self.avg_loss_r:.2f}R
Sample Size: {self.sample_size:,}
Expected R/Trade: {self.expected_r:.3f}
Kelly Fraction: {self.kelly_fraction:.1%} (Half-Kelly: {self.kelly_fraction/2:.1%})
"""


@dataclass
class RegimeModifiers:
    """Win rate modifiers by regime."""
    strong_uptrend: float = 1.05   # +5% win rate
    uptrend: float = 1.02          # +2% win rate
    ranging: float = 0.95          # -5% win rate
    downtrend: float = 0.90        # -10% win rate (for longs)
    strong_downtrend: float = 0.85
    volatile: float = 0.88
    crisis: float = 0.70

    def get_modifier(self, regime: str) -> float:
        """Get modifier for a regime."""
        regime = regime.lower().replace('_', '')
        return getattr(self, regime.replace(' ', ''), 1.0)


@dataclass
class DrawdownModifiers:
    """Win rate modifiers during drawdowns."""
    threshold_10pct: float = 0.98  # At 10% DD, reduce WR by 2%
    threshold_20pct: float = 0.95  # At 20% DD, reduce WR by 5%
    threshold_30pct: float = 0.90  # At 30% DD, reduce WR by 10%
    threshold_40pct: float = 0.80  # At 40% DD, reduce WR by 20%

    def get_modifier(self, drawdown_pct: float) -> float:
        """Get modifier based on current drawdown."""
        if drawdown_pct >= 0.40:
            return self.threshold_40pct
        elif drawdown_pct >= 0.30:
            return self.threshold_30pct
        elif drawdown_pct >= 0.20:
            return self.threshold_20pct
        elif drawdown_pct >= 0.10:
            return self.threshold_10pct
        return 1.0


@dataclass
class MonteCarloResult:
    """Complete Monte Carlo simulation results."""
    # Simulation parameters
    n_simulations: int
    n_trades_per_sim: int
    timeframe: str
    base_win_rate: float
    starting_capital: float
    risk_per_trade: float

    # Equity curves (n_simulations x n_trades+1)
    equity_curves: np.ndarray = field(repr=False)

    # Final balance statistics
    final_balances: np.ndarray = field(repr=False)
    median_balance: float = 0.0
    mean_balance: float = 0.0
    percentile_5: float = 0.0
    percentile_25: float = 0.0
    percentile_75: float = 0.0
    percentile_95: float = 0.0

    # Drawdown analysis
    max_drawdowns: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)
    avg_max_drawdown: float = 0.0
    worst_max_drawdown: float = 0.0

    # Risk metrics
    ruin_probability: float = 0.0  # P(balance < 10% of start)
    var_95: float = 0.0  # Value at Risk (95%)
    cvar_95: float = 0.0  # Conditional VaR

    # Expected value
    expected_r_per_trade: float = 0.0
    expected_final_r: float = 0.0

    # Kelly criterion
    kelly_fraction: float = 0.0
    half_kelly_fraction: float = 0.0
    optimal_risk_pct: float = 0.0

    # Confidence intervals on equity
    equity_ci_lower: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)
    equity_ci_upper: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)
    equity_median: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)
    equity_p25: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)
    equity_p75: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)

    def __str__(self):
        return f"""
Monte Carlo Results: {self.timeframe.upper()}
{'='*50}
Simulations: {self.n_simulations:,} x {self.n_trades_per_sim} trades
Base Win Rate: {self.base_win_rate:.1%}
Starting Capital: ${self.starting_capital:,.0f}
Risk per Trade: {self.risk_per_trade:.1%}

RISK METRICS
------------
Ruin Probability: {self.ruin_probability:.2%}
VaR (95%): ${self.var_95:,.0f}
CVaR (95%): ${self.cvar_95:,.0f}
Avg Max Drawdown: {self.avg_max_drawdown:.1%}
Worst Max Drawdown: {self.worst_max_drawdown:.1%}

RETURNS
-------
Expected R/Trade: {self.expected_r_per_trade:.3f}
Median Final Balance: ${self.median_balance:,.0f} ({(self.median_balance/self.starting_capital - 1)*100:+.1f}%)
5th Percentile: ${self.percentile_5:,.0f}
95th Percentile: ${self.percentile_95:,.0f}

POSITION SIZING
---------------
Full Kelly: {self.kelly_fraction:.1%}
Half Kelly: {self.half_kelly_fraction:.1%}
Optimal Risk: {self.optimal_risk_pct:.1%}
"""


class EnhancedMonteCarloSimulator:
    """
    Advanced Monte Carlo simulation engine.

    Features:
    - Separate simulations for different timeframe edges
    - Regime-aware win rate adjustments
    - Drawdown-sensitive risk reduction
    - Kelly criterion position sizing
    - Comprehensive risk metrics
    """

    def __init__(
        self,
        starting_capital: float = 10000,
        risk_per_trade: float = 0.02,
        regime_modifiers: RegimeModifiers = None,
        drawdown_modifiers: DrawdownModifiers = None,
        random_seed: int = 42,
    ):
        """
        Initialize Monte Carlo simulator.

        Args:
            starting_capital: Initial account balance
            risk_per_trade: Fraction of capital risked per trade (0.02 = 2%)
            regime_modifiers: Win rate adjustments by regime
            drawdown_modifiers: Win rate adjustments by drawdown
            random_seed: For reproducibility
        """
        self.starting_capital = starting_capital
        self.risk_per_trade = risk_per_trade
        self.regime_modifiers = regime_modifiers or RegimeModifiers()
        self.drawdown_modifiers = drawdown_modifiers or DrawdownModifiers()
        self.rng = np.random.default_rng(random_seed)

    def run_simulation(
        self,
        edge: TimeframeEdge,
        n_simulations: int = 10000,
        n_trades: int = 200,
        regime_sequence: List[str] = None,
        include_regime_effects: bool = False,
        include_drawdown_effects: bool = True,
        use_kelly_sizing: bool = False,
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation for a specific edge.

        Args:
            edge: TimeframeEdge with win rate and R:R
            n_simulations: Number of simulation paths
            n_trades: Number of trades per simulation
            regime_sequence: Optional regime path for each trade
            include_regime_effects: Apply regime modifiers
            include_drawdown_effects: Reduce WR during drawdowns
            use_kelly_sizing: Use Kelly criterion for position sizing

        Returns:
            MonteCarloResult with complete statistics
        """
        # Initialize equity curves
        equity_curves = np.zeros((n_simulations, n_trades + 1))
        equity_curves[:, 0] = self.starting_capital

        max_drawdowns = np.zeros(n_simulations)
        ruin_count = 0

        # Determine risk percentage
        if use_kelly_sizing:
            risk_pct = edge.kelly_fraction / 2  # Half Kelly
        else:
            risk_pct = self.risk_per_trade

        for sim in range(n_simulations):
            balance = self.starting_capital
            peak = balance

            for trade in range(n_trades):
                # Check for ruin
                if balance < self.starting_capital * 0.10:
                    ruin_count += 1
                    equity_curves[sim, trade+1:] = balance
                    break

                # Calculate effective win rate
                win_rate = edge.win_rate

                # Apply regime modifier
                if include_regime_effects and regime_sequence:
                    regime = regime_sequence[trade % len(regime_sequence)]
                    win_rate *= self.regime_modifiers.get_modifier(regime)

                # Apply drawdown modifier
                if include_drawdown_effects:
                    current_dd = (peak - balance) / peak if peak > 0 else 0
                    win_rate *= self.drawdown_modifiers.get_modifier(current_dd)

                # Clamp win rate
                win_rate = np.clip(win_rate, 0.01, 0.99)

                # Simulate trade
                risk_amount = balance * risk_pct

                if self.rng.random() < win_rate:
                    # Winner
                    balance += risk_amount * edge.avg_win_r
                else:
                    # Loser
                    balance -= risk_amount * edge.avg_loss_r

                # Update peak and equity
                peak = max(peak, balance)
                equity_curves[sim, trade + 1] = balance

            # Calculate max drawdown for this simulation
            running_max = np.maximum.accumulate(equity_curves[sim])
            drawdowns = (running_max - equity_curves[sim]) / running_max
            max_drawdowns[sim] = drawdowns.max()

        # Calculate statistics
        final_balances = equity_curves[:, -1]

        # Percentiles at each trade
        equity_ci_lower = np.percentile(equity_curves, 5, axis=0)
        equity_ci_upper = np.percentile(equity_curves, 95, axis=0)
        equity_median = np.percentile(equity_curves, 50, axis=0)
        equity_p25 = np.percentile(equity_curves, 25, axis=0)
        equity_p75 = np.percentile(equity_curves, 75, axis=0)

        # VaR and CVaR
        var_95 = self.starting_capital - np.percentile(final_balances, 5)
        worst_5pct = final_balances[final_balances <= np.percentile(final_balances, 5)]
        cvar_95 = self.starting_capital - worst_5pct.mean() if len(worst_5pct) > 0 else var_95

        result = MonteCarloResult(
            n_simulations=n_simulations,
            n_trades_per_sim=n_trades,
            timeframe=edge.timeframe,
            base_win_rate=edge.win_rate,
            starting_capital=self.starting_capital,
            risk_per_trade=risk_pct,
            equity_curves=equity_curves,
            final_balances=final_balances,
            median_balance=np.median(final_balances),
            mean_balance=np.mean(final_balances),
            percentile_5=np.percentile(final_balances, 5),
            percentile_25=np.percentile(final_balances, 25),
            percentile_75=np.percentile(final_balances, 75),
            percentile_95=np.percentile(final_balances, 95),
            max_drawdowns=max_drawdowns,
            avg_max_drawdown=max_drawdowns.mean(),
            worst_max_drawdown=max_drawdowns.max(),
            ruin_probability=ruin_count / n_simulations,
            var_95=var_95,
            cvar_95=cvar_95,
            expected_r_per_trade=edge.expected_r,
            expected_final_r=edge.expected_r * n_trades,
            kelly_fraction=edge.kelly_fraction,
            half_kelly_fraction=edge.kelly_fraction / 2,
            optimal_risk_pct=min(edge.kelly_fraction / 2, 0.05),
            equity_ci_lower=equity_ci_lower,
            equity_ci_upper=equity_ci_upper,
            equity_median=equity_median,
            equity_p25=equity_p25,
            equity_p75=equity_p75,
        )

        return result

    def stress_test_edge(
        self,
        edge: TimeframeEdge,
        n_simulations: int = 5000,
        n_trades: int = 200,
    ) -> Dict[str, MonteCarloResult]:
        """
        Run stress tests under various scenarios.

        Scenarios:
        - base_case: No modifications
        - regime_stress: Mostly adverse regimes
        - drawdown_stress: Start from 20% drawdown
        - ci_lower: Use lower bound of confidence interval

        Args:
            edge: TimeframeEdge to stress test
            n_simulations: Simulations per scenario
            n_trades: Trades per simulation

        Returns:
            Dict of scenario name to MonteCarloResult
        """
        results = {}

        # Base case
        results['base_case'] = self.run_simulation(
            edge, n_simulations, n_trades,
            include_regime_effects=False,
            include_drawdown_effects=False,
        )

        # With drawdown effects
        results['with_drawdown_effects'] = self.run_simulation(
            edge, n_simulations, n_trades,
            include_regime_effects=False,
            include_drawdown_effects=True,
        )

        # Adverse regime sequence (mostly downtrend/volatile)
        adverse_regimes = ['downtrend', 'volatile', 'ranging', 'volatile', 'downtrend']
        results['regime_stress'] = self.run_simulation(
            edge, n_simulations, n_trades,
            regime_sequence=adverse_regimes,
            include_regime_effects=True,
            include_drawdown_effects=True,
        )

        # Lower bound of confidence interval
        ci_lower_edge = TimeframeEdge(
            timeframe=f"{edge.timeframe}_ci_lower",
            win_rate=edge.confidence_interval[0],
            avg_win_r=edge.avg_win_r * 0.9,  # Also reduce avg win
            avg_loss_r=edge.avg_loss_r,
            sample_size=edge.sample_size,
            confidence_interval=edge.confidence_interval,
        )
        results['ci_lower_bound'] = self.run_simulation(
            ci_lower_edge, n_simulations, n_trades,
            include_drawdown_effects=True,
        )

        return results

    def compare_timeframes(
        self,
        daily_edge: TimeframeEdge,
        hourly_edge: TimeframeEdge,
        n_simulations: int = 10000,
        n_trades: int = 200,
    ) -> Dict[str, MonteCarloResult]:
        """
        Compare daily vs hourly edge performance.

        Args:
            daily_edge: Daily timeframe edge (e.g., 96% WR)
            hourly_edge: Hourly timeframe edge (e.g., 65% WR)
            n_simulations: Simulations per edge
            n_trades: Trades per simulation

        Returns:
            Dict with 'daily' and 'hourly' results
        """
        return {
            'daily': self.run_simulation(
                daily_edge, n_simulations, n_trades,
                include_drawdown_effects=True,
            ),
            'hourly': self.run_simulation(
                hourly_edge, n_simulations, n_trades,
                include_drawdown_effects=True,
            ),
        }


# ============================================================
# Utility Functions
# ============================================================

def kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
) -> float:
    """
    Calculate Kelly Criterion fraction.

    Formula: f* = (p * b - q) / b

    Where:
    - p = win probability
    - q = 1 - p (loss probability)
    - b = win/loss ratio

    Args:
        win_rate: Probability of winning (0-1)
        avg_win: Average win in R-multiples
        avg_loss: Average loss in R-multiples

    Returns:
        Kelly fraction (capped at 25%)
    """
    if avg_loss == 0 or avg_win == 0:
        return 0

    p = win_rate
    q = 1 - p
    b = avg_win / avg_loss

    kelly = (p * b - q) / b

    # Cap between 0 and 25%
    return max(0, min(0.25, kelly))


def wilson_confidence_interval(
    wins: int,
    total: int,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """
    Calculate Wilson score confidence interval for win rate.

    More accurate than normal approximation for small samples
    and extreme probabilities.

    Args:
        wins: Number of winning trades
        total: Total number of trades
        confidence: Confidence level (0.95 = 95%)

    Returns:
        (lower_bound, upper_bound) of win rate
    """
    if total == 0:
        return (0.0, 1.0)

    p = wins / total
    z = stats.norm.ppf((1 + confidence) / 2)
    n = total

    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denominator

    lower = max(0, center - margin)
    upper = min(1, center + margin)

    return (lower, upper)


def create_daily_edge(
    win_rate: float = 0.96,
    sample_size: int = 213,
) -> TimeframeEdge:
    """Create daily edge with default parameters."""
    return TimeframeEdge(
        timeframe='daily',
        win_rate=win_rate,
        avg_win_r=2.0,
        avg_loss_r=1.0,
        sample_size=sample_size,
    )


def create_hourly_edge(
    win_rate: float = 0.65,
    sample_size: int = 1221,
) -> TimeframeEdge:
    """Create hourly edge with default parameters."""
    return TimeframeEdge(
        timeframe='hourly',
        win_rate=win_rate,
        avg_win_r=2.0,
        avg_loss_r=1.0,
        sample_size=sample_size,
    )


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║             MONTE CARLO SIMULATION TEST                       ║
╚══════════════════════════════════════════════════════════════╝
""")

    # Create edges
    daily_edge = create_daily_edge(win_rate=0.96, sample_size=213)
    hourly_edge = create_hourly_edge(win_rate=0.65, sample_size=1221)

    print("=" * 60)
    print("EDGE COMPARISON")
    print("=" * 60)
    print(daily_edge)
    print(hourly_edge)

    # Run simulations
    print("=" * 60)
    print("RUNNING MONTE CARLO SIMULATIONS")
    print("=" * 60)

    simulator = EnhancedMonteCarloSimulator(
        starting_capital=10000,
        risk_per_trade=0.02,
    )

    print("\nSimulating 10,000 paths x 200 trades each...")

    # Compare timeframes
    comparison = simulator.compare_timeframes(daily_edge, hourly_edge)

    print("\n" + "=" * 60)
    print("DAILY EDGE RESULTS")
    print("=" * 60)
    print(comparison['daily'])

    print("\n" + "=" * 60)
    print("HOURLY EDGE RESULTS")
    print("=" * 60)
    print(comparison['hourly'])

    # Stress test daily edge
    print("\n" + "=" * 60)
    print("STRESS TESTING DAILY EDGE")
    print("=" * 60)

    stress_results = simulator.stress_test_edge(daily_edge, n_simulations=5000)

    print("\nScenario Results:")
    print("-" * 60)
    for scenario, result in stress_results.items():
        print(f"\n{scenario.upper()}:")
        print(f"  Ruin Probability: {result.ruin_probability:.2%}")
        print(f"  Median Balance: ${result.median_balance:,.0f}")
        print(f"  Avg Max Drawdown: {result.avg_max_drawdown:.1%}")

    # Summary comparison
    print("\n" + "=" * 60)
    print("SUMMARY: DAILY vs HOURLY")
    print("=" * 60)

    daily_r = comparison['daily']
    hourly_r = comparison['hourly']

    print(f"""
{'Metric':<25} {'Daily (96% WR)':<20} {'Hourly (65% WR)':<20}
{'-'*65}
{'Ruin Probability':<25} {daily_r.ruin_probability:.2%:<20} {hourly_r.ruin_probability:.2%:<20}
{'Median Final Balance':<25} ${daily_r.median_balance:,.0f:<19} ${hourly_r.median_balance:,.0f:<19}
{'Avg Max Drawdown':<25} {daily_r.avg_max_drawdown:.1%:<20} {hourly_r.avg_max_drawdown:.1%:<20}
{'Expected R/Trade':<25} {daily_r.expected_r_per_trade:.3f}R{'':<15} {hourly_r.expected_r_per_trade:.3f}R{'':<15}
{'Half Kelly':<25} {daily_r.half_kelly_fraction:.1%:<20} {hourly_r.half_kelly_fraction:.1%:<20}
""")

    daily_better = daily_r.median_balance > hourly_r.median_balance
    risk_better = daily_r.ruin_probability < hourly_r.ruin_probability

    print("\nCONCLUSION:")
    if daily_better and risk_better:
        print("  DAILY EDGE is superior in both returns AND risk metrics.")
        print("  Focus on daily timeframe for maximum edge.")
    elif daily_better:
        print("  DAILY EDGE has better returns but similar risk.")
    else:
        print("  Results are mixed. Consider both timeframes.")
