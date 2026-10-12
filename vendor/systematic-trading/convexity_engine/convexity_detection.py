"""
Acceleration and Convexity Detection
=====================================
CRITICAL for 0DTE options.
Detect speed of move, not just direction.
Speed = convexity = options payoff explosion.
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple


class ConvexityDetector:
    """
    Detects moments when options convexity explodes.

    Key metrics:
    - Price acceleration (change in velocity)
    - Range expansion vs historical
    - Momentum burst score
    - Gamma squeeze potential
    """

    def __init__(self):
        pass

    def calculate_acceleration_features(self, df: pd.DataFrame) -> dict:
        """
        Calculate acceleration and convexity features for ML model.

        Args:
            df: Intraday OHLCV data (1-min preferred)

        Returns:
            Dictionary of features
        """
        features = {
            'price_acceleration': 0,
            'price_acceleration_zscore': 0,
            'range_expansion_ratio': 0,
            'momentum_burst_score': 0,
            '1min_return': 0,
            '3min_return': 0,
            '5min_return': 0,
            '1min_acceleration': 0,
            '3bar_momentum_expansion': 0,
            'convexity_score': 0,
            'gamma_squeeze_potential': 0,
        }

        if len(df) < 20:
            return features

        df = df.copy()
        current_price = df['close'].iloc[-1]

        # Returns at different intervals
        if len(df) >= 2:
            features['1min_return'] = (current_price / df['close'].iloc[-2] - 1) * 100
        if len(df) >= 4:
            features['3min_return'] = (current_price / df['close'].iloc[-4] - 1) * 100
        if len(df) >= 6:
            features['5min_return'] = (current_price / df['close'].iloc[-6] - 1) * 100

        # Price velocity (1st derivative)
        df['velocity'] = df['close'].diff()

        # Price acceleration (2nd derivative - change in velocity)
        df['acceleration'] = df['velocity'].diff()

        features['price_acceleration'] = df['acceleration'].iloc[-1]

        # Acceleration z-score
        acc_mean = df['acceleration'].rolling(20).mean().iloc[-1]
        acc_std = df['acceleration'].rolling(20).std().iloc[-1]

        if acc_std > 0:
            features['price_acceleration_zscore'] = (features['price_acceleration'] - acc_mean) / acc_std

        # Range expansion ratio
        current_range = df['high'].iloc[-1] - df['low'].iloc[-1]
        avg_range = (df['high'] - df['low']).rolling(20).mean().iloc[-1]

        if avg_range > 0:
            features['range_expansion_ratio'] = current_range / avg_range

        # 3-bar momentum expansion
        if len(df) >= 4:
            momentum_now = abs(df['close'].iloc[-1] - df['close'].iloc[-4])
            momentum_prev = abs(df['close'].iloc[-4] - df['close'].iloc[-7]) if len(df) >= 7 else momentum_now

            if momentum_prev > 0:
                features['3bar_momentum_expansion'] = momentum_now / momentum_prev

        # 1-minute acceleration (for catching the burst)
        if len(df) >= 3:
            vel_now = df['velocity'].iloc[-1]
            vel_prev = df['velocity'].iloc[-2]
            features['1min_acceleration'] = vel_now - vel_prev

        # Momentum burst score
        features['momentum_burst_score'] = self._calculate_momentum_burst(df)

        # Convexity score (composite)
        features['convexity_score'] = self._calculate_convexity_score(features)

        # Gamma squeeze potential
        features['gamma_squeeze_potential'] = self._detect_gamma_squeeze(df, features)

        return features

    def _calculate_momentum_burst(self, df: pd.DataFrame) -> float:
        """
        Calculate momentum burst score (0-100).
        Identifies sudden explosive moves.
        """
        if len(df) < 10:
            return 0

        # Recent 3-bar move
        recent_move = abs(df['close'].iloc[-1] - df['close'].iloc[-4])

        # Historical distribution of 3-bar moves
        df_copy = df.copy()
        df_copy['3bar_move'] = abs(df_copy['close'] - df_copy['close'].shift(3))

        percentile = (df_copy['3bar_move'] < recent_move).mean() * 100

        return percentile

    def _calculate_convexity_score(self, features: dict) -> float:
        """
        Composite convexity score (0-100).
        Higher = more explosive options payoff potential.
        """
        score = 0

        # Acceleration contribution (max 30)
        acc_z = abs(features['price_acceleration_zscore'])
        score += min(acc_z * 10, 30)

        # Range expansion contribution (max 25)
        if features['range_expansion_ratio'] > 1.5:
            score += min((features['range_expansion_ratio'] - 1) * 25, 25)

        # Momentum burst contribution (max 25)
        score += features['momentum_burst_score'] * 0.25

        # Momentum expansion contribution (max 20)
        if features['3bar_momentum_expansion'] > 1.5:
            score += min((features['3bar_momentum_expansion'] - 1) * 20, 20)

        return min(score, 100)

    def _detect_gamma_squeeze(self, df: pd.DataFrame, features: dict) -> float:
        """
        Detect potential gamma squeeze conditions.

        Returns score 0-100.
        """
        score = 0

        # Fast directional move
        if abs(features['5min_return']) > 0.3:  # >0.3% in 5 mins
            score += 30

        # Accelerating
        if abs(features['price_acceleration_zscore']) > 2:
            score += 30

        # Volume increasing with move (if available)
        if len(df) >= 5 and 'volume' in df.columns:
            vol_now = df['volume'].iloc[-1]
            vol_5ago = df['volume'].iloc[-5]
            if vol_now > vol_5ago * 1.5:
                score += 20

        # Consecutive same-direction bars
        if len(df) >= 3:
            signs = np.sign(df['close'].diff().iloc[-3:])
            if (signs == signs.iloc[0]).all():
                score += 20

        return min(score, 100)

    def detect_convexity_opportunity(self, df: pd.DataFrame) -> Optional[dict]:
        """
        Detect high-convexity setup for 0DTE options.

        Returns:
            Signal dict or None
        """
        features = self.calculate_acceleration_features(df)

        # Need high convexity score
        if features['convexity_score'] < 50:
            return None

        current_price = df['close'].iloc[-1]

        # Determine direction from momentum
        if features['3min_return'] > 0.2:
            direction = 'LONG'  # Join the momentum
        elif features['3min_return'] < -0.2:
            direction = 'SHORT'
        else:
            return None

        return {
            'signal': 'CONVEXITY_BURST',
            'direction': direction,
            'entry': current_price,
            'convexity_score': features['convexity_score'],
            'gamma_squeeze_potential': features['gamma_squeeze_potential'],
            'acceleration': features['price_acceleration'],
            'momentum_burst': features['momentum_burst_score'],
            'timestamp': df.index[-1],
        }

    def calculate_options_convexity(self, underlying_move: float, time_to_expiry_hours: float,
                                     implied_vol: float = 0.20) -> dict:
        """
        Calculate expected 0DTE options convexity payoff.

        Args:
            underlying_move: Expected underlying move in %
            time_to_expiry_hours: Hours until expiration
            implied_vol: Implied volatility (decimal)

        Returns:
            Dict with payoff estimates
        """
        # Simplified Black-Scholes delta/gamma approximation
        # For ATM options near expiry

        time_years = time_to_expiry_hours / (252 * 6.5)  # Trading hours in year
        sqrt_time = np.sqrt(time_years)

        # ATM delta is ~0.5
        delta = 0.5

        # Gamma is highest ATM and near expiry
        # Approximate: gamma ≈ 1 / (S * sigma * sqrt(T))
        # For ATM, normalized gamma increases as T → 0

        # Expected option move (simplified)
        # Option move ≈ delta * underlying_move + 0.5 * gamma * underlying_move^2

        # For 0DTE, the gamma term dominates for large moves
        # This is the convexity!

        underlying_move_decimal = underlying_move / 100

        # Linear component
        linear_payoff = delta * underlying_move_decimal * 100

        # Convexity component (gamma)
        # Near expiry, this explodes for large moves
        convexity_multiplier = 1 / sqrt_time if sqrt_time > 0 else 10
        convexity_payoff = 0.5 * convexity_multiplier * (underlying_move_decimal ** 2) * 100

        total_payoff = linear_payoff + convexity_payoff

        return {
            'underlying_move_pct': underlying_move,
            'linear_payoff_pct': linear_payoff,
            'convexity_payoff_pct': convexity_payoff,
            'total_payoff_pct': total_payoff,
            'convexity_ratio': convexity_payoff / linear_payoff if linear_payoff > 0 else 0,
            'time_to_expiry_hours': time_to_expiry_hours,
        }
