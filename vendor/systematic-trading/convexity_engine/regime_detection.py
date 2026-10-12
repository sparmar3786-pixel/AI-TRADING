"""
Market Regime Detection
========================
Two key regime classifiers:
1. Trend Day Detection - Is this session a trend day?
2. Gamma Feedback Loop - Will dealer hedging amplify moves?

Output feeds into strategy adaptation.
"""

import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import pickle
import os

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


class MarketRegime(Enum):
    """Market regime classification."""
    MEAN_REVERSION = "mean_reversion"
    TREND_DAY = "trend_day"
    GAMMA_EXPANSION = "gamma_expansion"


@dataclass
class RegimeState:
    """Current market regime state."""
    regime: MarketRegime
    trend_day_probability: float
    gamma_expansion_probability: float
    confidence: float
    features: Dict

    def to_dict(self) -> dict:
        return {
            'regime': self.regime.value,
            'trend_day_probability': self.trend_day_probability,
            'gamma_expansion_probability': self.gamma_expansion_probability,
            'confidence': self.confidence,
        }


# =============================================================================
# TREND DAY DETECTION
# =============================================================================

class TrendDayDetector:
    """
    Detects whether current session is likely a trend day.

    A trend day:
    - Breaks opening range and sustains
    - Doesn't revert to VWAP meaningfully
    - Closes near session extremes
    - Range > 1.5x average daily range
    """

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler() if HAS_SKLEARN else None
        self.is_trained = False
        self.avg_daily_range = None

    def calculate_opening_range(self, df: pd.DataFrame, minutes: int = 30) -> dict:
        """
        Calculate opening range features.

        Args:
            df: Intraday data with datetime index
            minutes: Opening range duration

        Returns:
            Opening range features
        """
        features = {
            'or_high': np.nan,
            'or_low': np.nan,
            'or_range': np.nan,
            'or_breakout_distance': 0,
            'or_breakout_direction': 0,
            'or_momentum_slope': 0,
        }

        if len(df) < 10:
            return features

        # Get session start
        try:
            first_bar_time = df.index[0]
            if hasattr(first_bar_time, 'time'):
                session_start = first_bar_time.replace(hour=9, minute=30, second=0)
            else:
                session_start = pd.to_datetime(first_bar_time).replace(hour=9, minute=30, second=0)

            or_end = session_start + timedelta(minutes=minutes)

            # Filter to opening range
            or_mask = (df.index >= session_start) & (df.index <= or_end)
            or_df = df[or_mask]

            if len(or_df) < 2:
                return features

            features['or_high'] = or_df['high'].max()
            features['or_low'] = or_df['low'].min()
            features['or_range'] = features['or_high'] - features['or_low']

            # Current price vs opening range
            current_price = df['close'].iloc[-1]

            if current_price > features['or_high']:
                features['or_breakout_distance'] = current_price - features['or_high']
                features['or_breakout_direction'] = 1
            elif current_price < features['or_low']:
                features['or_breakout_distance'] = features['or_low'] - current_price
                features['or_breakout_direction'] = -1

            # Opening range momentum slope
            if len(or_df) >= 2:
                slope = (or_df['close'].iloc[-1] - or_df['close'].iloc[0]) / len(or_df)
                features['or_momentum_slope'] = slope

        except Exception as e:
            pass

        return features

    def calculate_vwap_behavior(self, df: pd.DataFrame) -> dict:
        """Calculate VWAP-related features."""
        features = {
            'vwap': np.nan,
            'distance_from_vwap': 0,
            'vwap_crosses': 0,
            'time_above_vwap_pct': 0,
            'time_below_vwap_pct': 0,
        }

        if len(df) < 10:
            return features

        df = df.copy()

        # Calculate VWAP
        if 'volume' in df.columns:
            df['typical'] = (df['high'] + df['low'] + df['close']) / 3
            df['cum_vol'] = df['volume'].cumsum()
            df['cum_val'] = (df['typical'] * df['volume']).cumsum()
            df['vwap'] = df['cum_val'] / df['cum_vol']
        else:
            # Approximate VWAP as running mean of typical price
            df['typical'] = (df['high'] + df['low'] + df['close']) / 3
            df['vwap'] = df['typical'].expanding().mean()

        current_vwap = df['vwap'].iloc[-1]
        current_price = df['close'].iloc[-1]

        features['vwap'] = current_vwap
        features['distance_from_vwap'] = current_price - current_vwap

        # Count VWAP crosses
        df['above_vwap'] = df['close'] > df['vwap']
        crosses = (df['above_vwap'] != df['above_vwap'].shift(1)).sum()
        features['vwap_crosses'] = crosses

        # Time spent above/below VWAP
        above_count = df['above_vwap'].sum()
        total = len(df)
        features['time_above_vwap_pct'] = above_count / total * 100
        features['time_below_vwap_pct'] = (total - above_count) / total * 100

        return features

    def calculate_trend_day_features(self, df: pd.DataFrame, daily_df: pd.DataFrame = None) -> dict:
        """
        Calculate all features for trend day detection.

        Args:
            df: Intraday data
            daily_df: Daily data for context (optional)

        Returns:
            Feature dictionary
        """
        features = {}

        if len(df) < 20:
            return self._default_features()

        # Opening range features
        or_features = self.calculate_opening_range(df)
        features.update(or_features)

        # VWAP behavior
        vwap_features = self.calculate_vwap_behavior(df)
        features.update(vwap_features)

        # Session range
        session_high = df['high'].max()
        session_low = df['low'].min()
        session_range = session_high - session_low
        current_price = df['close'].iloc[-1]

        features['session_range'] = session_range
        features['session_high'] = session_high
        features['session_low'] = session_low

        # Close location in range (0 = at low, 1 = at high)
        if session_range > 0:
            features['close_location'] = (current_price - session_low) / session_range
        else:
            features['close_location'] = 0.5

        # Range vs average
        if daily_df is not None and len(daily_df) >= 20:
            avg_daily_range = (daily_df['high'] - daily_df['low']).rolling(20).mean().iloc[-1]
            self.avg_daily_range = avg_daily_range
        elif self.avg_daily_range is not None:
            avg_daily_range = self.avg_daily_range
        else:
            # Estimate from intraday
            avg_daily_range = session_range  # Fallback

        features['avg_daily_range'] = avg_daily_range
        features['range_expansion_ratio'] = session_range / avg_daily_range if avg_daily_range > 0 else 1

        # ATR ratio
        df_copy = df.copy()
        df_copy['tr'] = np.maximum(
            df_copy['high'] - df_copy['low'],
            np.maximum(
                abs(df_copy['high'] - df_copy['close'].shift(1)),
                abs(df_copy['low'] - df_copy['close'].shift(1))
            )
        )
        current_atr = df_copy['tr'].rolling(14).mean().iloc[-1]
        features['intraday_atr'] = current_atr

        # Volatility
        returns = df['close'].pct_change()
        features['intraday_volatility'] = returns.std() * np.sqrt(len(df)) * 100

        # Momentum consistency
        df_copy['direction'] = np.sign(df_copy['close'].diff())
        features['momentum_consistency'] = abs(df_copy['direction'].sum()) / len(df_copy)

        # Time features
        try:
            first_time = df.index[0]
            last_time = df.index[-1]
            if hasattr(first_time, 'hour'):
                features['minutes_since_open'] = (last_time.hour - 9) * 60 + (last_time.minute - 30)
                features['minutes_to_close'] = (16 - last_time.hour) * 60 - last_time.minute
            else:
                features['minutes_since_open'] = 0
                features['minutes_to_close'] = 390
        except:
            features['minutes_since_open'] = 0
            features['minutes_to_close'] = 390

        return features

    def _default_features(self) -> dict:
        """Return default features."""
        return {
            'or_high': np.nan,
            'or_low': np.nan,
            'or_range': np.nan,
            'or_breakout_distance': 0,
            'or_breakout_direction': 0,
            'or_momentum_slope': 0,
            'vwap': np.nan,
            'distance_from_vwap': 0,
            'vwap_crosses': 0,
            'time_above_vwap_pct': 50,
            'time_below_vwap_pct': 50,
            'session_range': 0,
            'range_expansion_ratio': 1,
            'close_location': 0.5,
            'momentum_consistency': 0,
            'minutes_since_open': 0,
            'minutes_to_close': 390,
        }

    def predict_trend_day_probability(self, features: dict) -> float:
        """
        Predict probability that current session is a trend day.

        Uses rule-based scoring if model not trained.
        """
        if self.is_trained and self.model is not None:
            # Use ML model
            feature_values = [features.get(f, 0) for f in self._get_feature_names()]
            X = np.array([feature_values])
            X = np.nan_to_num(X, nan=0)
            X_scaled = self.scaler.transform(X)
            prob = self.model.predict_proba(X_scaled)[0][1]
            return prob * 100

        # Rule-based scoring
        score = 0

        # Opening range breakout (max 25)
        if features.get('or_breakout_direction', 0) != 0:
            score += 15
            breakout_dist = features.get('or_breakout_distance', 0)
            or_range = features.get('or_range', 1)
            if or_range > 0 and breakout_dist > or_range:
                score += 10

        # Range expansion (max 25)
        range_ratio = features.get('range_expansion_ratio', 1)
        if range_ratio > 1.5:
            score += 25
        elif range_ratio > 1.2:
            score += 15
        elif range_ratio > 1.0:
            score += 5

        # VWAP behavior (max 25)
        vwap_crosses = features.get('vwap_crosses', 10)
        if vwap_crosses <= 2:
            score += 25  # Few crosses = trending
        elif vwap_crosses <= 4:
            score += 15
        elif vwap_crosses <= 6:
            score += 5

        # Time on one side of VWAP (max 15)
        time_above = features.get('time_above_vwap_pct', 50)
        time_below = features.get('time_below_vwap_pct', 50)
        dominant_side = max(time_above, time_below)
        if dominant_side > 80:
            score += 15
        elif dominant_side > 70:
            score += 10
        elif dominant_side > 60:
            score += 5

        # Close location (max 10)
        close_loc = features.get('close_location', 0.5)
        if close_loc > 0.8 or close_loc < 0.2:
            score += 10
        elif close_loc > 0.7 or close_loc < 0.3:
            score += 5

        return min(score, 100)

    def _get_feature_names(self) -> list:
        """Get feature names for ML model."""
        return [
            'or_breakout_distance', 'or_breakout_direction', 'or_momentum_slope',
            'distance_from_vwap', 'vwap_crosses', 'time_above_vwap_pct',
            'range_expansion_ratio', 'close_location', 'momentum_consistency',
            'minutes_since_open',
        ]


# =============================================================================
# GAMMA FEEDBACK LOOP DETECTION
# =============================================================================

class GammaFeedbackDetector:
    """
    Detects when dealer hedging may amplify price movement.

    Gamma feedback occurs when:
    - Price approaches large option strikes
    - Intraday velocity accelerates
    - Hedging forces push price further
    """

    def __init__(self, symbol: str = 'SPY'):
        self.symbol = symbol
        self.model = None
        self.scaler = StandardScaler() if HAS_SKLEARN else None
        self.is_trained = False

        # Strike intervals
        self.strike_interval = 1 if symbol == 'SPY' else 1

    def calculate_strike_proximity(self, current_price: float) -> dict:
        """Calculate distance to key strike levels."""
        features = {
            'distance_to_nearest_strike': 0,
            'distance_to_round_strike': 0,
            'strike_proximity_score': 0,
        }

        # Nearest $1 strike
        nearest_strike = round(current_price)
        features['distance_to_nearest_strike'] = abs(current_price - nearest_strike)

        # Nearest $5 round strike
        round_strike = round(current_price / 5) * 5
        features['distance_to_round_strike'] = abs(current_price - round_strike)

        # Proximity score (higher = closer to strikes)
        # Max score when exactly at a strike
        dist_score = max(0, 1 - features['distance_to_nearest_strike'])
        round_score = max(0, 1 - features['distance_to_round_strike'] / 2.5)

        features['strike_proximity_score'] = (dist_score * 40 + round_score * 60)

        return features

    def calculate_velocity_features(self, df: pd.DataFrame) -> dict:
        """Calculate price velocity and acceleration."""
        features = {
            'velocity_1m': 0,
            'velocity_5m': 0,
            'velocity_zscore': 0,
            'acceleration': 0,
            'acceleration_zscore': 0,
        }

        if len(df) < 10:
            return features

        df = df.copy()

        # Calculate average bar range
        avg_range = (df['high'] - df['low']).mean()
        if avg_range <= 0:
            avg_range = 0.01

        # 1-bar velocity
        if len(df) >= 2:
            move_1m = abs(df['close'].iloc[-1] - df['close'].iloc[-2])
            features['velocity_1m'] = move_1m / avg_range

        # 5-bar velocity
        if len(df) >= 6:
            move_5m = abs(df['close'].iloc[-1] - df['close'].iloc[-6])
            avg_5m_range = avg_range * 5
            features['velocity_5m'] = move_5m / avg_5m_range

        # Velocity z-score
        df['velocity'] = abs(df['close'].diff())
        vel_mean = df['velocity'].rolling(20).mean().iloc[-1]
        vel_std = df['velocity'].rolling(20).std().iloc[-1]
        if vel_std > 0:
            features['velocity_zscore'] = (df['velocity'].iloc[-1] - vel_mean) / vel_std

        # Acceleration (change in velocity)
        if len(df) >= 6:
            vel_now = features['velocity_5m']
            # Velocity 5 bars ago
            move_prev = abs(df['close'].iloc[-6] - df['close'].iloc[-11]) if len(df) >= 11 else move_5m
            vel_prev = move_prev / avg_5m_range
            features['acceleration'] = vel_now - vel_prev

        # Acceleration z-score
        df['accel'] = df['velocity'].diff()
        accel_mean = df['accel'].rolling(20).mean().iloc[-1]
        accel_std = df['accel'].rolling(20).std().iloc[-1]
        if accel_std > 0:
            features['acceleration_zscore'] = (df['accel'].iloc[-1] - accel_mean) / accel_std

        return features

    def calculate_range_expansion(self, df: pd.DataFrame) -> dict:
        """Calculate intraday range expansion."""
        features = {
            'range_expansion_ratio': 1,
            'range_percentile': 50,
        }

        if len(df) < 20:
            return features

        # Current intraday range
        current_range = df['high'].max() - df['low'].min()

        # Average range over bars
        avg_bar_range = (df['high'] - df['low']).mean()
        expected_range = avg_bar_range * np.sqrt(len(df))

        if expected_range > 0:
            features['range_expansion_ratio'] = current_range / expected_range

        # Range percentile
        df_copy = df.copy()
        df_copy['bar_range'] = df_copy['high'] - df_copy['low']
        current_bar_range = df_copy['bar_range'].iloc[-1]
        percentile = (df_copy['bar_range'] < current_bar_range).mean() * 100
        features['range_percentile'] = percentile

        return features

    def calculate_time_sensitivity(self, timestamp: datetime) -> dict:
        """Calculate time-based sensitivity factors."""
        features = {
            'minutes_since_open': 0,
            'minutes_to_close': 390,
            'is_power_hour': 0,
            'is_opening_30': 0,
            'time_decay_factor': 1.0,
        }

        try:
            current_time = timestamp.time() if hasattr(timestamp, 'time') else timestamp

            # Minutes since open
            open_minutes = 9 * 60 + 30
            current_minutes = current_time.hour * 60 + current_time.minute
            features['minutes_since_open'] = max(0, current_minutes - open_minutes)

            # Minutes to close
            close_minutes = 16 * 60
            features['minutes_to_close'] = max(0, close_minutes - current_minutes)

            # Power hour (2:30 PM - 4:00 PM)
            if current_time.hour >= 14 and current_time.minute >= 30:
                features['is_power_hour'] = 1

            # Opening 30 minutes
            if features['minutes_since_open'] <= 30:
                features['is_opening_30'] = 1

            # Time decay factor (increases near close)
            hours_to_close = features['minutes_to_close'] / 60
            if hours_to_close > 0:
                features['time_decay_factor'] = 1 / (hours_to_close + 0.5)
            else:
                features['time_decay_factor'] = 2.0

        except:
            pass

        return features

    def calculate_liquidity_proxy(self, df: pd.DataFrame) -> dict:
        """Calculate liquidity thinning proxies."""
        features = {
            'volume_ratio': 1.0,
            'spread_proxy': 0,
            'liquidity_score': 50,
        }

        if len(df) < 20:
            return features

        # Volume ratio (if available)
        if 'volume' in df.columns:
            current_vol = df['volume'].iloc[-1]
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            if avg_vol > 0:
                features['volume_ratio'] = current_vol / avg_vol

        # Spread proxy: high-low range vs close
        df_copy = df.copy()
        df_copy['spread_proxy'] = (df_copy['high'] - df_copy['low']) / df_copy['close'] * 100
        current_spread = df_copy['spread_proxy'].iloc[-1]
        avg_spread = df_copy['spread_proxy'].rolling(20).mean().iloc[-1]

        features['spread_proxy'] = current_spread

        # Liquidity score (lower = thinner liquidity)
        # Low volume + wide spreads = thin liquidity
        vol_score = min(features['volume_ratio'] * 50, 50)
        spread_score = 50 - min((current_spread / avg_spread - 1) * 25, 25) if avg_spread > 0 else 50
        features['liquidity_score'] = vol_score + spread_score

        return features

    def calculate_gamma_feedback_features(self, df: pd.DataFrame, timestamp: datetime) -> dict:
        """Calculate all gamma feedback features."""
        features = {}

        current_price = df['close'].iloc[-1]

        # Strike proximity
        strike_features = self.calculate_strike_proximity(current_price)
        features.update(strike_features)

        # Velocity
        velocity_features = self.calculate_velocity_features(df)
        features.update(velocity_features)

        # Range expansion
        range_features = self.calculate_range_expansion(df)
        features.update(range_features)

        # Time sensitivity
        time_features = self.calculate_time_sensitivity(timestamp)
        features.update(time_features)

        # Liquidity
        liquidity_features = self.calculate_liquidity_proxy(df)
        features.update(liquidity_features)

        return features

    def predict_gamma_expansion_probability(self, features: dict) -> float:
        """
        Predict probability of gamma-driven expansion.

        Uses weighted composite score.
        """
        if self.is_trained and self.model is not None:
            # Use ML model
            feature_values = [features.get(f, 0) for f in self._get_feature_names()]
            X = np.array([feature_values])
            X = np.nan_to_num(X, nan=0)
            X_scaled = self.scaler.transform(X)
            prob = self.model.predict_proba(X_scaled)[0][1]
            return prob * 100

        # Rule-based composite score
        # gamma_feedback_score = w1*strike_proximity + w2*velocity + w3*acceleration
        #                       + w4*range_expansion + w5*time_decay

        w1, w2, w3, w4, w5 = 0.20, 0.25, 0.20, 0.20, 0.15

        # Normalize components to 0-100
        strike_score = features.get('strike_proximity_score', 0)

        velocity_z = abs(features.get('velocity_zscore', 0))
        velocity_score = min(velocity_z * 25, 100)

        accel_z = abs(features.get('acceleration_zscore', 0))
        accel_score = min(accel_z * 25, 100)

        range_ratio = features.get('range_expansion_ratio', 1)
        range_score = min((range_ratio - 1) * 50 + 50, 100) if range_ratio > 1 else range_ratio * 50

        time_factor = features.get('time_decay_factor', 1)
        time_score = min(time_factor * 40, 100)

        # Power hour / opening boost
        if features.get('is_power_hour', 0) or features.get('is_opening_30', 0):
            time_score = min(time_score * 1.3, 100)

        gamma_score = (
            w1 * strike_score +
            w2 * velocity_score +
            w3 * accel_score +
            w4 * range_score +
            w5 * time_score
        )

        return min(gamma_score, 100)

    def _get_feature_names(self) -> list:
        """Get feature names for ML model."""
        return [
            'strike_proximity_score', 'velocity_5m', 'velocity_zscore',
            'acceleration', 'acceleration_zscore', 'range_expansion_ratio',
            'time_decay_factor', 'is_power_hour', 'liquidity_score',
        ]


# =============================================================================
# MARKET REGIME CLASSIFIER
# =============================================================================

class MarketRegimeClassifier:
    """
    Combines Trend Day and Gamma Feedback models to classify current regime.

    Regimes:
    - GAMMA_EXPANSION: Dealer hedging amplifying moves (highest priority)
    - TREND_DAY: Sustained directional session
    - MEAN_REVERSION: Normal, range-bound trading
    """

    def __init__(self, symbol: str = 'SPY'):
        self.symbol = symbol
        self.trend_detector = TrendDayDetector()
        self.gamma_detector = GammaFeedbackDetector(symbol)

        # Thresholds
        self.gamma_threshold = 60  # Above this = gamma expansion regime
        self.trend_threshold = 65  # Above this = trend day regime

    def classify_regime(self, df: pd.DataFrame, timestamp: datetime,
                        daily_df: pd.DataFrame = None) -> RegimeState:
        """
        Classify current market regime.

        Args:
            df: Intraday data
            timestamp: Current timestamp
            daily_df: Daily data for context

        Returns:
            RegimeState with probabilities and classification
        """
        # Calculate trend day features and probability
        trend_features = self.trend_detector.calculate_trend_day_features(df, daily_df)
        trend_prob = self.trend_detector.predict_trend_day_probability(trend_features)

        # Calculate gamma features and probability
        gamma_features = self.gamma_detector.calculate_gamma_feedback_features(df, timestamp)
        gamma_prob = self.gamma_detector.predict_gamma_expansion_probability(gamma_features)

        # Classify regime (gamma takes priority)
        if gamma_prob > self.gamma_threshold:
            regime = MarketRegime.GAMMA_EXPANSION
            confidence = gamma_prob
        elif trend_prob > self.trend_threshold:
            regime = MarketRegime.TREND_DAY
            confidence = trend_prob
        else:
            regime = MarketRegime.MEAN_REVERSION
            confidence = 100 - max(gamma_prob, trend_prob)

        # Combine features
        all_features = {**trend_features, **gamma_features}

        return RegimeState(
            regime=regime,
            trend_day_probability=trend_prob,
            gamma_expansion_probability=gamma_prob,
            confidence=confidence,
            features=all_features,
        )

    def get_strategy_adaptation(self, regime_state: RegimeState) -> dict:
        """
        Get strategy adaptation based on current regime.

        Returns trading guidance.
        """
        adaptations = {
            MarketRegime.MEAN_REVERSION: {
                'regime': 'mean_reversion',
                'favor': [
                    'Supply/demand zone reversals',
                    'VWAP reversion trades',
                    'Liquidity sweep fades',
                    'Overextension reversals',
                ],
                'avoid': [
                    'Chasing momentum',
                    'Breakout entries',
                    'Trend continuation',
                ],
                'position_size_mult': 1.0,
                'stop_mult': 1.0,
                'target_mult': 1.0,
            },
            MarketRegime.TREND_DAY: {
                'regime': 'trend_day',
                'favor': [
                    'Pullbacks in trend direction',
                    'VWAP continuation trades',
                    'Breakout continuation',
                    'Add to winners',
                ],
                'avoid': [
                    'Fading moves',
                    'Counter-trend entries',
                    'Mean reversion trades',
                ],
                'position_size_mult': 1.2,
                'stop_mult': 1.5,  # Wider stops for trend days
                'target_mult': 2.0,  # Larger targets
            },
            MarketRegime.GAMMA_EXPANSION: {
                'regime': 'gamma_expansion',
                'favor': [
                    'Momentum entries',
                    'Breakout acceleration',
                    'Continuation through strikes',
                    'Quick scalps with momentum',
                ],
                'avoid': [
                    'Counter-trend entries',
                    'Fading gamma moves',
                    'Large position sizes (volatility)',
                ],
                'position_size_mult': 0.8,  # Smaller size due to volatility
                'stop_mult': 1.5,
                'target_mult': 2.5,  # Gamma moves can be large
            },
        }

        adaptation = adaptations.get(regime_state.regime, adaptations[MarketRegime.MEAN_REVERSION])

        # Add probabilities
        adaptation['trend_day_probability'] = regime_state.trend_day_probability
        adaptation['gamma_expansion_probability'] = regime_state.gamma_expansion_probability
        adaptation['confidence'] = regime_state.confidence

        return adaptation

    def print_regime_analysis(self, regime_state: RegimeState):
        """Print regime analysis."""
        print("\n" + "=" * 60)
        print("MARKET REGIME ANALYSIS")
        print("=" * 60)

        print(f"\nCurrent Regime: {regime_state.regime.value.upper()}")
        print(f"Confidence: {regime_state.confidence:.1f}%")

        print(f"\nProbabilities:")
        print(f"  Trend Day: {regime_state.trend_day_probability:.1f}%")
        print(f"  Gamma Expansion: {regime_state.gamma_expansion_probability:.1f}%")

        adaptation = self.get_strategy_adaptation(regime_state)

        print(f"\nStrategy Adaptation:")
        print(f"  Favor:")
        for item in adaptation['favor'][:3]:
            print(f"    • {item}")
        print(f"  Avoid:")
        for item in adaptation['avoid'][:2]:
            print(f"    • {item}")

        print(f"\n  Position Size: {adaptation['position_size_mult']:.1f}x")
        print(f"  Stop Width: {adaptation['stop_mult']:.1f}x")
        print(f"  Target: {adaptation['target_mult']:.1f}x")

        print("=" * 60)
