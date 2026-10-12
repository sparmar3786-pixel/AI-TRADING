"""
HMM-based Market Regime Detection
==================================
Uses Hidden Markov Models to:
1. Identify latent market states from observables
2. Predict regime transitions 1-5 bars ahead
3. Smooth regime classifications (avoid rapid flipping)
4. Calculate transition probability matrices

Key advantage over rules-based: Probabilistic, predictive, adaptive.

Dependencies: hmmlearn, numpy, pandas, scikit-learn
"""

import os
import sys
import pickle
import numpy as np
import pandas as pd
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum

from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HMMState(Enum):
    """Hidden states discovered by HMM."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"


@dataclass
class HMMRegimeResult:
    """Result of HMM regime analysis."""
    # Current state
    current_state: int
    current_state_name: str
    state_probabilities: np.ndarray  # Probability of each state

    # Transition predictions
    next_bar_probs: np.ndarray  # P(state | next bar)
    five_bar_probs: np.ndarray  # P(state | 5 bars ahead)

    # Transition matrix info
    transition_matrix: np.ndarray
    mean_holding_time: Dict[int, float]  # Expected bars in each state

    # Confidence and signals
    regime_confidence: float  # 0-100
    is_transition_likely: bool  # True if P(change) > 0.3

    # Mapping to existing regimes
    mapped_regime: str  # Maps to MarketRegime enum value

    def __str__(self):
        return f"""
HMM Regime Analysis
==================
Current State: {self.current_state_name} (confidence: {self.regime_confidence:.1f}%)
State Probabilities: {[f'{p:.1%}' for p in self.state_probabilities]}

Next Bar Forecast: {[f'{p:.1%}' for p in self.next_bar_probs]}
5-Bar Forecast: {[f'{p:.1%}' for p in self.five_bar_probs]}

Transition Likely: {'Yes' if self.is_transition_likely else 'No'}
Mapped Regime: {self.mapped_regime}
"""


class HMMRegimeDetector:
    """
    Hidden Markov Model based regime detector.

    Learns latent market states from observable indicators,
    providing probabilistic regime classification and
    transition forecasts.

    States:
        0: trending_up - Strong upward momentum
        1: trending_down - Strong downward momentum
        2: ranging - Low volatility, no clear direction
        3: volatile - High volatility, uncertain direction

    Observations:
        - ADX (trend strength)
        - ATR percentile (volatility)
        - Trend strength (-100 to +100)
        - RSI (momentum)
        - Volume ratio
    """

    STATE_NAMES = {
        0: "trending_up",
        1: "trending_down",
        2: "ranging",
        3: "volatile",
    }

    REGIME_MAPPING = {
        "trending_up": "UPTREND",
        "trending_down": "DOWNTREND",
        "ranging": "RANGING",
        "volatile": "VOLATILE",
    }

    def __init__(
        self,
        n_states: int = 4,
        n_iter: int = 100,
        covariance_type: str = 'full',
        random_state: int = 42,
        min_observations: int = 50,
    ):
        """
        Initialize HMM Regime Detector.

        Args:
            n_states: Number of hidden states (3-5 recommended)
            n_iter: Training iterations
            covariance_type: 'full', 'diag', 'spherical', 'tied'
            random_state: For reproducibility
            min_observations: Minimum bars needed for fitting
        """
        self.n_states = n_states
        self.min_observations = min_observations

        self.model = GaussianHMM(
            n_components=n_states,
            covariance_type=covariance_type,
            n_iter=n_iter,
            random_state=random_state,
        )

        self.scaler = StandardScaler()
        self.is_fitted = False
        self.state_characteristics: Dict[int, Dict] = {}
        self.fitted_at: Optional[datetime] = None

    def prepare_observations(
        self,
        df: pd.DataFrame,
        vix_level: float = None,
    ) -> np.ndarray:
        """
        Extract observation features from OHLCV data.

        Features:
            1. ADX - Trend strength (0-100)
            2. ATR percentile - Volatility ranking (0-100)
            3. Trend strength - Directional bias (-100 to +100)
            4. RSI - Momentum (0-100)
            5. Volume ratio - Relative volume

        Args:
            df: DataFrame with OHLCV data
            vix_level: Optional VIX value

        Returns:
            np.ndarray of shape (n_bars, n_features)
        """
        df = df.copy()

        # 1. ADX calculation
        df['adx'] = self._calculate_adx(df)

        # 2. ATR percentile
        atr = self._calculate_atr(df)
        df['atr_pct'] = atr.rank(pct=True) * 100

        # 3. Trend strength
        df['trend_strength'] = self._calculate_trend_strength(df)

        # 4. RSI
        df['rsi'] = self._calculate_rsi(df)

        # 5. Volume ratio
        if 'volume' in df.columns:
            df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
            df['vol_ratio'] = df['vol_ratio'].fillna(1.0).clip(0, 5)
        else:
            df['vol_ratio'] = 1.0

        # Select features and handle NaN
        features = ['adx', 'atr_pct', 'trend_strength', 'rsi', 'vol_ratio']
        observations = df[features].fillna(method='ffill').fillna(method='bfill').fillna(50)

        return observations.values

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average Directional Index."""
        high = df['high']
        low = df['low']
        close = df['close']

        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()

        # Directional Movement
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(period).mean()

        return adx.fillna(25)  # Default to moderate trend

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(period).mean()

    def _calculate_trend_strength(self, df: pd.DataFrame) -> pd.Series:
        """Calculate trend strength from -100 to +100."""
        close = df['close']

        # SMAs
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()

        # Components
        above_sma20 = (close > sma20).astype(int) * 25 - 12.5
        above_sma50 = (close > sma50).astype(int) * 25 - 12.5
        sma_aligned = (sma20 > sma50).astype(int) * 25 - 12.5

        # Price momentum
        momentum = close.pct_change(10) * 100
        momentum = momentum.clip(-25, 25)

        trend_strength = above_sma20 + above_sma50 + sma_aligned + momentum

        return trend_strength.fillna(0).clip(-100, 100)

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        return rsi.fillna(50)

    def fit(
        self,
        df: pd.DataFrame,
        vix_level: float = None,
    ) -> 'HMMRegimeDetector':
        """
        Fit HMM on historical data.

        Args:
            df: DataFrame with OHLCV data (50+ bars required)
            vix_level: Optional VIX value

        Returns:
            self (fitted detector)
        """
        if len(df) < self.min_observations:
            raise ValueError(
                f"Insufficient data: {len(df)} bars. "
                f"Need at least {self.min_observations}."
            )

        # Prepare observations
        observations = self.prepare_observations(df, vix_level)

        # Scale features
        observations_scaled = self.scaler.fit_transform(observations)

        # Fit HMM
        self.model.fit(observations_scaled)

        # Analyze state characteristics
        self._analyze_state_characteristics(observations, df)

        self.is_fitted = True
        self.fitted_at = datetime.now()

        return self

    def _analyze_state_characteristics(
        self,
        observations: np.ndarray,
        df: pd.DataFrame,
    ):
        """Analyze and label the discovered states."""
        observations_scaled = self.scaler.transform(observations)
        states = self.model.predict(observations_scaled)

        feature_names = ['adx', 'atr_pct', 'trend_strength', 'rsi', 'vol_ratio']

        for state in range(self.n_states):
            mask = states == state
            if mask.sum() == 0:
                continue

            state_obs = observations[mask]

            self.state_characteristics[state] = {
                'mean_adx': state_obs[:, 0].mean(),
                'mean_atr_pct': state_obs[:, 1].mean(),
                'mean_trend': state_obs[:, 2].mean(),
                'mean_rsi': state_obs[:, 3].mean(),
                'mean_vol': state_obs[:, 4].mean(),
                'count': mask.sum(),
                'pct_of_data': mask.mean() * 100,
            }

        # Map states to regime names based on characteristics
        self._map_states_to_regimes()

    def _map_states_to_regimes(self):
        """Map HMM states to regime names based on characteristics."""
        state_scores = {}

        for state, chars in self.state_characteristics.items():
            # Score for trending up: high trend strength, moderate+ ADX
            up_score = chars['mean_trend'] + chars['mean_adx'] * 0.5

            # Score for trending down: low trend strength, moderate+ ADX
            down_score = -chars['mean_trend'] + chars['mean_adx'] * 0.5

            # Score for ranging: low ADX, moderate volatility
            ranging_score = (50 - chars['mean_adx']) + (50 - abs(chars['mean_trend']))

            # Score for volatile: high ATR percentile, high ADX variation
            volatile_score = chars['mean_atr_pct'] + chars['mean_vol'] * 10

            state_scores[state] = {
                'trending_up': up_score,
                'trending_down': down_score,
                'ranging': ranging_score,
                'volatile': volatile_score,
            }

        # Assign each state to highest scoring regime
        assigned = set()
        self.state_to_regime = {}

        # Sort states by max score to assign most confident first
        sorted_states = sorted(
            state_scores.keys(),
            key=lambda s: max(state_scores[s].values()),
            reverse=True
        )

        for state in sorted_states:
            scores = state_scores[state]
            # Get best available regime
            sorted_regimes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            for regime, score in sorted_regimes:
                if regime not in assigned:
                    self.state_to_regime[state] = regime
                    assigned.add(regime)
                    break
            else:
                # If all regimes assigned, use best score
                self.state_to_regime[state] = sorted_regimes[0][0]

    def predict_current_state(
        self,
        df: pd.DataFrame,
        vix_level: float = None,
    ) -> HMMRegimeResult:
        """
        Predict current regime state with probabilities.

        Args:
            df: Recent OHLCV data (at least 50 bars)
            vix_level: Optional VIX value

        Returns:
            HMMRegimeResult with current state and predictions
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted. Call fit() first.")

        # Prepare and scale observations
        observations = self.prepare_observations(df, vix_level)
        observations_scaled = self.scaler.transform(observations)

        # Get state sequence and probabilities
        state_sequence = self.model.predict(observations_scaled)
        state_probs = self.model.predict_proba(observations_scaled)

        current_state = state_sequence[-1]
        current_probs = state_probs[-1]

        # Get transition matrix
        trans_matrix = self.model.transmat_

        # Predict next bar probabilities
        next_bar_probs = trans_matrix[current_state]

        # Predict 5 bars ahead
        five_bar_matrix = np.linalg.matrix_power(trans_matrix, 5)
        five_bar_probs = five_bar_matrix[current_state]

        # Calculate holding times
        holding_times = {}
        for s in range(self.n_states):
            p_stay = trans_matrix[s, s]
            if p_stay < 1:
                holding_times[s] = 1 / (1 - p_stay)
            else:
                holding_times[s] = float('inf')

        # Confidence: max probability
        confidence = current_probs.max() * 100

        # Transition likely: P(change) > 0.3
        p_stay = current_probs[current_state]
        is_transition_likely = (1 - p_stay) > 0.3

        # Map to regime
        state_name = self.state_to_regime.get(current_state, "unknown")
        mapped_regime = self.REGIME_MAPPING.get(state_name, "UNKNOWN")

        return HMMRegimeResult(
            current_state=current_state,
            current_state_name=state_name,
            state_probabilities=current_probs,
            next_bar_probs=next_bar_probs,
            five_bar_probs=five_bar_probs,
            transition_matrix=trans_matrix,
            mean_holding_time=holding_times,
            regime_confidence=confidence,
            is_transition_likely=is_transition_likely,
            mapped_regime=mapped_regime,
        )

    def predict_transitions(
        self,
        current_state: int,
        n_steps: int = 5,
    ) -> np.ndarray:
        """
        Predict regime probabilities n_steps ahead.

        Args:
            current_state: Current state index
            n_steps: Number of steps to forecast

        Returns:
            Array of shape (n_steps, n_states) with probabilities
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted. Call fit() first.")

        trans_matrix = self.model.transmat_
        predictions = np.zeros((n_steps, self.n_states))

        for step in range(n_steps):
            step_matrix = np.linalg.matrix_power(trans_matrix, step + 1)
            predictions[step] = step_matrix[current_state]

        return predictions

    def smooth_predictions(
        self,
        df: pd.DataFrame,
        min_hold_bars: int = 5,
        vix_level: float = None,
    ) -> pd.Series:
        """
        Apply smoothing to avoid rapid regime flipping.

        Uses Viterbi algorithm for optimal state sequence,
        then enforces minimum hold constraint.

        Args:
            df: OHLCV data
            min_hold_bars: Minimum bars to hold a regime
            vix_level: Optional VIX value

        Returns:
            Series of smoothed state indices
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted. Call fit() first.")

        observations = self.prepare_observations(df, vix_level)
        observations_scaled = self.scaler.transform(observations)

        # Use Viterbi for optimal sequence
        _, state_sequence = self.model.decode(observations_scaled, algorithm='viterbi')

        # Apply minimum hold constraint
        smoothed = self._apply_min_hold(state_sequence, min_hold_bars)

        return pd.Series(smoothed, index=df.index[-len(smoothed):])

    def _apply_min_hold(
        self,
        states: np.ndarray,
        min_hold: int,
    ) -> np.ndarray:
        """Apply minimum hold constraint to state sequence."""
        smoothed = states.copy()

        i = 0
        while i < len(smoothed):
            current = smoothed[i]
            # Find how long this state lasts
            j = i
            while j < len(smoothed) and smoothed[j] == current:
                j += 1

            duration = j - i

            # If too short and not at end, extend to min_hold or merge
            if duration < min_hold and i > 0:
                # Merge with previous state
                smoothed[i:j] = smoothed[i-1]

            i = j

        return smoothed

    def get_transition_matrix(self) -> np.ndarray:
        """Get the transition probability matrix."""
        if not self.is_fitted:
            raise ValueError("Model not fitted. Call fit() first.")
        return self.model.transmat_

    def get_state_summary(self) -> pd.DataFrame:
        """Get summary statistics for each state."""
        if not self.state_characteristics:
            raise ValueError("Model not fitted. Call fit() first.")

        rows = []
        for state, chars in self.state_characteristics.items():
            regime_name = self.state_to_regime.get(state, "unknown")
            rows.append({
                'State': state,
                'Regime': regime_name,
                'Avg ADX': f"{chars['mean_adx']:.1f}",
                'Avg ATR%': f"{chars['mean_atr_pct']:.1f}",
                'Avg Trend': f"{chars['mean_trend']:.1f}",
                'Avg RSI': f"{chars['mean_rsi']:.1f}",
                '% of Data': f"{chars['pct_of_data']:.1f}%",
            })

        return pd.DataFrame(rows)

    def save_model(self, path: str = None) -> str:
        """
        Save fitted HMM model.

        Args:
            path: Save path (default: ml/trained_models/hmm_regime.pkl)

        Returns:
            Path where model was saved
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted. Call fit() first.")

        if path is None:
            models_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'trained_models'
            )
            os.makedirs(models_dir, exist_ok=True)
            path = os.path.join(models_dir, 'hmm_regime.pkl')

        save_data = {
            'model': self.model,
            'scaler': self.scaler,
            'n_states': self.n_states,
            'state_characteristics': self.state_characteristics,
            'state_to_regime': self.state_to_regime,
            'fitted_at': self.fitted_at,
        }

        with open(path, 'wb') as f:
            pickle.dump(save_data, f)

        print(f"HMM model saved to: {path}")
        return path

    @classmethod
    def load_model(cls, path: str) -> 'HMMRegimeDetector':
        """
        Load fitted HMM model.

        Args:
            path: Path to saved model

        Returns:
            Fitted HMMRegimeDetector
        """
        with open(path, 'rb') as f:
            save_data = pickle.load(f)

        detector = cls(n_states=save_data['n_states'])
        detector.model = save_data['model']
        detector.scaler = save_data['scaler']
        detector.state_characteristics = save_data['state_characteristics']
        detector.state_to_regime = save_data['state_to_regime']
        detector.fitted_at = save_data['fitted_at']
        detector.is_fitted = True

        return detector


# ============================================================
# Quick Functions
# ============================================================

def fit_hmm_on_symbol(
    symbol: str = 'SPY',
    period: str = '6mo',
    n_states: int = 4,
) -> HMMRegimeDetector:
    """
    Quick function to fit HMM on a symbol.

    Args:
        symbol: Stock symbol
        period: Data period ('6mo', '1y', '2y')
        n_states: Number of hidden states

    Returns:
        Fitted HMMRegimeDetector
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)

        if len(df) < 50:
            raise ValueError(f"Insufficient data for {symbol}")

        # Normalize column names
        df.columns = [c.lower() for c in df.columns]

        detector = HMMRegimeDetector(n_states=n_states)
        detector.fit(df)

        return detector

    except ImportError:
        raise ImportError("yfinance required. Install with: pip install yfinance")


def predict_regime(
    df: pd.DataFrame,
    model_path: str = None,
) -> HMMRegimeResult:
    """
    Quick prediction using saved or new model.

    Args:
        df: OHLCV DataFrame
        model_path: Path to saved model (optional)

    Returns:
        HMMRegimeResult
    """
    if model_path and os.path.exists(model_path):
        detector = HMMRegimeDetector.load_model(model_path)
    else:
        detector = HMMRegimeDetector()
        detector.fit(df)

    return detector.predict_current_state(df)


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║                 HMM REGIME DETECTION TEST                     ║
╚══════════════════════════════════════════════════════════════╝
""")

    try:
        import yfinance as yf

        print("Fetching SPY data...")
        ticker = yf.Ticker('SPY')
        df = ticker.history(period='1y')
        df.columns = [c.lower() for c in df.columns]

        print(f"Got {len(df)} bars")

        # Fit HMM
        print("\nFitting HMM with 4 states...")
        detector = HMMRegimeDetector(n_states=4)
        detector.fit(df)

        # Show state summary
        print("\nState Characteristics:")
        print(detector.get_state_summary().to_string(index=False))

        # Predict current state
        print("\nCurrent Regime Analysis:")
        result = detector.predict_current_state(df)
        print(result)

        # Show transition matrix
        print("\nTransition Matrix:")
        trans_df = pd.DataFrame(
            detector.get_transition_matrix(),
            index=[f"From {detector.state_to_regime.get(i, i)}" for i in range(4)],
            columns=[f"To {detector.state_to_regime.get(i, i)}" for i in range(4)],
        )
        print(trans_df.round(3).to_string())

        # Save model
        detector.save_model()

    except ImportError:
        print("yfinance not available. Install with: pip install yfinance")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
