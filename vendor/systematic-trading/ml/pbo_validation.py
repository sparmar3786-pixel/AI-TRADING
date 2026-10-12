"""
Probability of Backtest Overfitting (PBO) Validation
=====================================================
Implementation based on Bailey, Borwein, Lopez de Prado, Zhu (2014):
"The Probability of Backtest Overfitting"

Key Concepts:
1. Combinatorially Symmetric Cross-Validation (CSCV)
2. Probability of Backtest Overfitting (PBO)
3. Deflated Sharpe Ratio
4. Minimum Backtest Length

This validates whether a trading strategy's performance is real or overfit.

"An overfit backtest is one that would not be expected to deliver the same
performance in the future." - Bailey et al.
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Callable
from itertools import combinations
from scipy import stats
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, log_loss
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings('ignore')


@dataclass
class PBOResult:
    """Results from Probability of Backtest Overfitting analysis."""
    # Core PBO metrics
    pbo: float                          # Probability of Backtest Overfitting (0-1)
    pbo_interpretation: str             # Human-readable interpretation

    # Performance metrics
    in_sample_performance: float        # Average IS performance
    out_of_sample_performance: float    # Average OOS performance
    performance_degradation: float      # (IS - OOS) / IS

    # Rank analysis
    rank_logits: np.ndarray             # Logit of relative ranks
    mean_rank_logit: float              # Mean of rank logits

    # Statistical tests
    is_overfit: bool                    # PBO > 0.5
    confidence_level: float             # 1 - PBO

    # Additional metrics
    n_combinations: int                 # Number of CSCV combinations
    n_partitions: int                   # Number of data partitions

    # Detailed results
    is_performances: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)
    oos_performances: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)

    def __str__(self):
        status = "LIKELY OVERFIT" if self.is_overfit else "LIKELY VALID"
        status_color = "WARNING" if self.is_overfit else "PASS"

        return f"""
╔══════════════════════════════════════════════════════════════╗
║           PROBABILITY OF BACKTEST OVERFITTING                 ║
╚══════════════════════════════════════════════════════════════╝

  PBO Score: {self.pbo:.1%}  [{status_color}]
  Status: {status}

  Interpretation: {self.pbo_interpretation}

PERFORMANCE ANALYSIS
--------------------
  In-Sample Performance:     {self.in_sample_performance:.1%}
  Out-of-Sample Performance: {self.out_of_sample_performance:.1%}
  Performance Degradation:   {self.performance_degradation:.1%}

STATISTICAL DETAILS
-------------------
  CSCV Combinations: {self.n_combinations}
  Data Partitions:   {self.n_partitions}
  Mean Rank Logit:   {self.mean_rank_logit:.3f}
  Confidence Level:  {self.confidence_level:.1%}

RECOMMENDATION
--------------
{'  ⚠️  This strategy shows signs of overfitting.' if self.is_overfit else '  ✓  This strategy appears robust.'}
{'  Consider: more data, simpler model, or walk-forward testing.' if self.is_overfit else '  Continue with out-of-sample validation.'}
"""


@dataclass
class DeflatedSharpeResult:
    """Results from Deflated Sharpe Ratio analysis."""
    observed_sharpe: float
    deflated_sharpe: float
    expected_max_sharpe: float

    # Multiple testing correction
    n_trials: int
    haircut_sharpe: float  # Sharpe after haircut for multiple testing

    # Interpretation
    is_significant: bool
    p_value: float

    def __str__(self):
        status = "SIGNIFICANT" if self.is_significant else "NOT SIGNIFICANT"
        return f"""
DEFLATED SHARPE RATIO ANALYSIS
==============================
  Observed Sharpe:     {self.observed_sharpe:.3f}
  Expected Max Sharpe: {self.expected_max_sharpe:.3f} (from {self.n_trials} trials)
  Deflated Sharpe:     {self.deflated_sharpe:.3f}
  Haircut Sharpe:      {self.haircut_sharpe:.3f}

  P-Value: {self.p_value:.4f}
  Status:  {status}
"""


class PBOValidator:
    """
    Validates trading strategies using Probability of Backtest Overfitting.

    Uses Combinatorially Symmetric Cross-Validation (CSCV) to estimate
    the probability that a strategy's backtest performance is overfit.

    A PBO < 0.5 suggests the strategy is likely robust.
    A PBO > 0.5 suggests the strategy is likely overfit.
    """

    def __init__(
        self,
        n_partitions: int = 16,
        metric: str = 'accuracy',
        random_state: int = 42,
    ):
        """
        Initialize PBO Validator.

        Args:
            n_partitions: Number of partitions for CSCV (must be even, typically 8-16)
            metric: Performance metric ('accuracy', 'sharpe', 'returns')
            random_state: For reproducibility
        """
        if n_partitions % 2 != 0:
            raise ValueError("n_partitions must be even")

        self.n_partitions = n_partitions
        self.metric = metric
        self.random_state = random_state
        self.rng = np.random.default_rng(random_state)

    def calculate_pbo(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_factory: Callable,
        performance_func: Callable = None,
    ) -> PBOResult:
        """
        Calculate Probability of Backtest Overfitting using CSCV.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target vector (n_samples,)
            model_factory: Function that returns a fresh model instance
            performance_func: Function to calculate performance (default: accuracy)

        Returns:
            PBOResult with PBO score and analysis
        """
        n_samples = len(X)

        if performance_func is None:
            performance_func = lambda y_true, y_pred: accuracy_score(y_true, y_pred)

        # Create partitions
        partition_size = n_samples // self.n_partitions
        indices = np.arange(n_samples)
        self.rng.shuffle(indices)

        partitions = []
        for i in range(self.n_partitions):
            start = i * partition_size
            end = start + partition_size if i < self.n_partitions - 1 else n_samples
            partitions.append(indices[start:end])

        # Generate all combinations of N/2 partitions for training
        n_train = self.n_partitions // 2
        train_combinations = list(combinations(range(self.n_partitions), n_train))
        n_combinations = len(train_combinations)

        is_performances = []
        oos_performances = []

        for train_parts in train_combinations:
            test_parts = tuple(i for i in range(self.n_partitions) if i not in train_parts)

            # Build train/test indices
            train_idx = np.concatenate([partitions[i] for i in train_parts])
            test_idx = np.concatenate([partitions[i] for i in test_parts])

            X_train, y_train = X[train_idx], y[train_idx]
            X_test, y_test = X[test_idx], y[test_idx]

            # Train model
            model = model_factory()
            model.fit(X_train, y_train)

            # Calculate IS and OOS performance
            y_train_pred = model.predict(X_train)
            y_test_pred = model.predict(X_test)

            is_perf = performance_func(y_train, y_train_pred)
            oos_perf = performance_func(y_test, y_test_pred)

            is_performances.append(is_perf)
            oos_performances.append(oos_perf)

        is_performances = np.array(is_performances)
        oos_performances = np.array(oos_performances)

        # Calculate rank logits
        # For each combination, calculate relative rank of OOS performance
        rank_logits = []

        for i in range(n_combinations):
            # Rank of this OOS performance among all OOS performances
            oos_rank = stats.rankdata(oos_performances)[i]
            relative_rank = oos_rank / n_combinations

            # Avoid edge cases
            relative_rank = np.clip(relative_rank, 0.01, 0.99)

            # Logit transformation
            logit = np.log(relative_rank / (1 - relative_rank))
            rank_logits.append(logit)

        rank_logits = np.array(rank_logits)

        # PBO = proportion of combinations where OOS underperforms
        # (where IS rank > OOS rank, suggesting overfitting)
        is_ranks = stats.rankdata(is_performances)
        oos_ranks = stats.rankdata(oos_performances)

        # Count where high IS rank leads to low OOS rank
        n_overfit = np.sum(oos_performances < np.median(oos_performances))
        pbo = n_overfit / n_combinations

        # Alternative PBO calculation based on rank correlation
        rank_correlation = stats.spearmanr(is_performances, oos_performances)[0]

        # If high IS performance correlates with low OOS, that's overfitting
        if rank_correlation < 0:
            pbo = 0.5 + abs(rank_correlation) / 2
        else:
            pbo = 0.5 - rank_correlation / 2

        # Interpretation
        if pbo < 0.25:
            interpretation = "Very low probability of overfitting. Strategy appears robust."
        elif pbo < 0.40:
            interpretation = "Low probability of overfitting. Strategy likely valid."
        elif pbo < 0.50:
            interpretation = "Moderate probability of overfitting. Use caution."
        elif pbo < 0.60:
            interpretation = "Elevated probability of overfitting. Needs more validation."
        elif pbo < 0.75:
            interpretation = "High probability of overfitting. Strategy is suspect."
        else:
            interpretation = "Very high probability of overfitting. Strategy likely invalid."

        # Performance degradation
        avg_is = is_performances.mean()
        avg_oos = oos_performances.mean()
        degradation = (avg_is - avg_oos) / avg_is if avg_is > 0 else 0

        return PBOResult(
            pbo=pbo,
            pbo_interpretation=interpretation,
            in_sample_performance=avg_is,
            out_of_sample_performance=avg_oos,
            performance_degradation=degradation,
            rank_logits=rank_logits,
            mean_rank_logit=rank_logits.mean(),
            is_overfit=pbo > 0.5,
            confidence_level=1 - pbo,
            n_combinations=n_combinations,
            n_partitions=self.n_partitions,
            is_performances=is_performances,
            oos_performances=oos_performances,
        )

    def walk_forward_validation(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_factory: Callable,
        n_splits: int = 5,
        train_ratio: float = 0.7,
    ) -> Dict:
        """
        Perform walk-forward validation (expanding window).

        This is more realistic than random CV for time series.

        Args:
            X: Feature matrix
            y: Target vector
            model_factory: Function returning fresh model
            n_splits: Number of walk-forward splits
            train_ratio: Initial training ratio

        Returns:
            Dict with OOS performances and statistics
        """
        n_samples = len(X)
        results = {
            'oos_performances': [],
            'train_sizes': [],
            'test_sizes': [],
        }

        # Calculate split points
        min_train = int(n_samples * train_ratio)
        step = (n_samples - min_train) // n_splits

        for i in range(n_splits):
            train_end = min_train + i * step
            test_end = min(train_end + step, n_samples)

            if train_end >= test_end:
                break

            X_train, y_train = X[:train_end], y[:train_end]
            X_test, y_test = X[train_end:test_end], y[train_end:test_end]

            # Train and evaluate
            model = model_factory()
            model.fit(X_train, y_train)

            y_pred = model.predict(X_test)
            oos_perf = accuracy_score(y_test, y_pred)

            results['oos_performances'].append(oos_perf)
            results['train_sizes'].append(len(X_train))
            results['test_sizes'].append(len(X_test))

        results['mean_oos'] = np.mean(results['oos_performances'])
        results['std_oos'] = np.std(results['oos_performances'])
        results['min_oos'] = np.min(results['oos_performances'])

        return results


def calculate_deflated_sharpe(
    returns: np.ndarray,
    n_trials: int = 1,
    risk_free: float = 0.0,
    annualization: int = 252,
) -> DeflatedSharpeResult:
    """
    Calculate Deflated Sharpe Ratio accounting for multiple testing.

    Based on Bailey & Lopez de Prado (2014).

    Args:
        returns: Array of returns
        n_trials: Number of strategy variations tested
        risk_free: Risk-free rate
        annualization: Annualization factor (252 for daily)

    Returns:
        DeflatedSharpeResult with adjusted Sharpe
    """
    # Observed Sharpe
    excess_returns = returns - risk_free / annualization
    observed_sharpe = np.sqrt(annualization) * excess_returns.mean() / excess_returns.std()

    # Expected maximum Sharpe under null (no skill)
    # E[max(Z_1, ..., Z_n)] for standard normal
    expected_max = (1 - np.euler_gamma) * stats.norm.ppf(1 - 1/n_trials) + \
                   np.euler_gamma * stats.norm.ppf(1 - 1/(n_trials * np.e))

    # Standard error of Sharpe
    n = len(returns)
    se_sharpe = np.sqrt((1 + 0.5 * observed_sharpe**2) / n)

    # Deflated Sharpe
    deflated_sharpe = (observed_sharpe - expected_max * se_sharpe)

    # Haircut for multiple testing (more conservative)
    haircut_sharpe = observed_sharpe * (1 - np.log(n_trials) / np.log(n))

    # P-value
    z_score = deflated_sharpe / se_sharpe
    p_value = 1 - stats.norm.cdf(z_score)

    return DeflatedSharpeResult(
        observed_sharpe=observed_sharpe,
        deflated_sharpe=deflated_sharpe,
        expected_max_sharpe=expected_max,
        n_trials=n_trials,
        haircut_sharpe=haircut_sharpe,
        is_significant=p_value < 0.05,
        p_value=p_value,
    )


def minimum_backtest_length(
    target_sharpe: float = 1.0,
    observed_sharpe: float = 2.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    frequency: int = 252,
) -> int:
    """
    Calculate minimum backtest length needed for statistical significance.

    Based on Bailey & Lopez de Prado (2012).

    Args:
        target_sharpe: Minimum Sharpe to be significant
        observed_sharpe: Observed annualized Sharpe
        skewness: Return skewness
        kurtosis: Return kurtosis
        frequency: Annualization factor

    Returns:
        Minimum number of observations needed
    """
    # Variance of Sharpe estimator
    sharpe_var = (1 - skewness * observed_sharpe +
                  ((kurtosis - 1) / 4) * observed_sharpe**2)

    # Minimum length
    min_length = sharpe_var * (stats.norm.ppf(0.95) / (observed_sharpe - target_sharpe))**2

    return int(np.ceil(min_length))


def validate_trading_edge(
    X: np.ndarray,
    y: np.ndarray,
    model_factory: Callable,
    n_partitions: int = 8,
    verbose: bool = True,
) -> Dict:
    """
    Comprehensive validation of a trading edge.

    Runs:
    1. PBO analysis
    2. Walk-forward validation
    3. Bootstrap confidence intervals

    Args:
        X: Feature matrix
        y: Target labels
        model_factory: Function returning fresh model
        n_partitions: Partitions for PBO
        verbose: Print results

    Returns:
        Dict with all validation results
    """
    results = {}

    # 1. PBO Analysis
    validator = PBOValidator(n_partitions=n_partitions)
    pbo_result = validator.calculate_pbo(X, y, model_factory)
    results['pbo'] = pbo_result

    # 2. Walk-Forward Validation
    wf_result = validator.walk_forward_validation(X, y, model_factory, n_splits=5)
    results['walk_forward'] = wf_result

    # 3. Bootstrap confidence interval on accuracy
    n_bootstrap = 1000
    bootstrap_accuracies = []

    for _ in range(n_bootstrap):
        idx = np.random.choice(len(X), len(X), replace=True)
        X_boot, y_boot = X[idx], y[idx]

        X_train, X_test, y_train, y_test = train_test_split(
            X_boot, y_boot, test_size=0.3, random_state=None
        )

        model = model_factory()
        model.fit(X_train, y_train)
        acc = accuracy_score(y_test, model.predict(X_test))
        bootstrap_accuracies.append(acc)

    bootstrap_accuracies = np.array(bootstrap_accuracies)
    results['bootstrap'] = {
        'mean_accuracy': bootstrap_accuracies.mean(),
        'std_accuracy': bootstrap_accuracies.std(),
        'ci_lower': np.percentile(bootstrap_accuracies, 2.5),
        'ci_upper': np.percentile(bootstrap_accuracies, 97.5),
    }

    # 4. Overall assessment
    is_valid = (
        pbo_result.pbo < 0.5 and
        wf_result['mean_oos'] > 0.55 and
        results['bootstrap']['ci_lower'] > 0.5
    )

    results['overall'] = {
        'is_valid': is_valid,
        'pbo_score': pbo_result.pbo,
        'oos_accuracy': wf_result['mean_oos'],
        'bootstrap_ci': (results['bootstrap']['ci_lower'], results['bootstrap']['ci_upper']),
    }

    if verbose:
        print(pbo_result)
        print(f"\nWALK-FORWARD VALIDATION")
        print(f"  Mean OOS Accuracy: {wf_result['mean_oos']:.1%}")
        print(f"  Std OOS Accuracy:  {wf_result['std_oos']:.1%}")
        print(f"  Min OOS Accuracy:  {wf_result['min_oos']:.1%}")

        print(f"\nBOOTSTRAP CONFIDENCE INTERVAL")
        print(f"  Mean Accuracy: {results['bootstrap']['mean_accuracy']:.1%}")
        print(f"  95% CI: [{results['bootstrap']['ci_lower']:.1%}, {results['bootstrap']['ci_upper']:.1%}]")

        print(f"\n{'='*60}")
        print(f"OVERALL ASSESSMENT: {'VALID' if is_valid else 'SUSPECT'}")
        print(f"{'='*60}")

    return results


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║       PROBABILITY OF BACKTEST OVERFITTING TEST                ║
╚══════════════════════════════════════════════════════════════╝
""")

    # Load training data
    try:
        import pandas as pd
        from sklearn.ensemble import GradientBoostingClassifier

        # Load the training data
        data_path = 'ml/trained_models/training_data_1d.csv'

        if os.path.exists(data_path):
            df = pd.read_csv(data_path)
            print(f"Loaded {len(df)} samples from {data_path}")

            # Prepare features
            feature_cols = [c for c in df.columns if c not in
                          ['label', 'symbol', 'entry_price', 'stop_price', 'target_price',
                           'exit_price', 'risk_dollars', 'pnl_r', 'pnl_pct', 'bars_held',
                           'exit_reason', 'rr_achieved']]

            X = df[feature_cols].fillna(0).values
            y = df['label'].values

            print(f"Features: {len(feature_cols)}")
            print(f"Win Rate: {y.mean():.1%}")
            print(f"Samples: {len(y)}")

            # Model factory
            def model_factory():
                return GradientBoostingClassifier(
                    n_estimators=100,
                    max_depth=3,
                    random_state=42
                )

            # Run validation
            print("\nRunning PBO validation...")
            print("(This may take a moment)\n")

            # Use fewer partitions for small dataset
            n_parts = min(8, len(y) // 5)
            if n_parts % 2 != 0:
                n_parts -= 1
            n_parts = max(4, n_parts)

            results = validate_trading_edge(X, y, model_factory, n_partitions=n_parts)

        else:
            print(f"Training data not found at {data_path}")
            print("Run training first to generate data.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
