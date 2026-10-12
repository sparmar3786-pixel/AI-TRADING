"""
Volatility Regime Layer
========================
Market behavior changes dramatically with volatility.
VIX-based regime classification affects all signals.
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
from enum import Enum


class VolatilityRegime(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class VolatilityRegimeDetector:
    """
    Classifies market volatility regime using VIX and price-based metrics.

    Regimes:
    - LOW: VIX < 15 (grinding, low premium)
    - MEDIUM: VIX 15-20 (normal trading)
    - HIGH: VIX 20-30 (elevated fear, good for reversals)
    - EXTREME: VIX > 30 (crisis, gamma squeezes)
    """

    def __init__(self):
        self.regime_thresholds = {
            'low': 15,
            'medium': 20,
            'high': 30,
        }

    def classify_regime(self, vix_level: float) -> VolatilityRegime:
        """
        Classify current regime based on VIX level.
        """
        if vix_level < self.regime_thresholds['low']:
            return VolatilityRegime.LOW
        elif vix_level < self.regime_thresholds['medium']:
            return VolatilityRegime.MEDIUM
        elif vix_level < self.regime_thresholds['high']:
            return VolatilityRegime.HIGH
        else:
            return VolatilityRegime.EXTREME

    def calculate_vix_features(self, vix_df: pd.DataFrame) -> dict:
        """
        Calculate VIX-based features.

        Args:
            vix_df: DataFrame with VIX OHLCV data

        Returns:
            Dictionary of VIX features
        """
        features = {
            'vix_level': 0,
            'vix_change_1d': 0,
            'vix_change_5d': 0,
            'vix_percentile_20d': 0,
            'vix_intraday_momentum': 0,
            'vix_term_structure': 0,  # Contango/backwardation proxy
            'regime': 'medium',
            'regime_numeric': 1,
        }

        if len(vix_df) < 20:
            return features

        current_vix = vix_df['close'].iloc[-1]
        features['vix_level'] = current_vix

        # VIX changes
        if len(vix_df) >= 2:
            features['vix_change_1d'] = current_vix - vix_df['close'].iloc[-2]

        if len(vix_df) >= 6:
            features['vix_change_5d'] = current_vix - vix_df['close'].iloc[-6]

        # VIX percentile (where is current VIX relative to last 20 days)
        vix_20d = vix_df['close'].iloc[-20:]
        features['vix_percentile_20d'] = (vix_20d < current_vix).mean() * 100

        # Intraday momentum (today's move)
        if 'open' in vix_df.columns:
            today_open = vix_df['open'].iloc[-1]
            features['vix_intraday_momentum'] = (current_vix - today_open) / today_open * 100

        # Term structure proxy (VIX vs 5-day MA - contango indicator)
        vix_ma5 = vix_df['close'].rolling(5).mean().iloc[-1]
        features['vix_term_structure'] = (current_vix - vix_ma5) / vix_ma5 * 100

        # Classify regime
        regime = self.classify_regime(current_vix)
        features['regime'] = regime.value
        features['regime_numeric'] = {
            'low': 0,
            'medium': 1,
            'high': 2,
            'extreme': 3
        }.get(regime.value, 1)

        return features

    def calculate_realized_vol_features(self, price_df: pd.DataFrame) -> dict:
        """
        Calculate realized volatility features from price data.

        Args:
            price_df: Price DataFrame with OHLCV

        Returns:
            Dictionary of realized vol features
        """
        features = {
            'realized_vol_5d': 0,
            'realized_vol_20d': 0,
            'vol_ratio': 0,  # Short-term vs long-term vol
            'vol_expansion': 0,
            'intraday_vol': 0,
            'overnight_gap_vol': 0,
        }

        if len(price_df) < 20:
            return features

        # Daily returns
        returns = price_df['close'].pct_change()

        # Realized volatility (annualized)
        features['realized_vol_5d'] = returns.iloc[-5:].std() * np.sqrt(252) * 100
        features['realized_vol_20d'] = returns.iloc[-20:].std() * np.sqrt(252) * 100

        # Vol ratio (short-term vs long-term)
        if features['realized_vol_20d'] > 0:
            features['vol_ratio'] = features['realized_vol_5d'] / features['realized_vol_20d']

        # Vol expansion (current 5d vol vs prior 5d vol)
        if len(price_df) >= 10:
            prior_5d_vol = returns.iloc[-10:-5].std() * np.sqrt(252) * 100
            if prior_5d_vol > 0:
                features['vol_expansion'] = features['realized_vol_5d'] / prior_5d_vol

        # Intraday volatility (high-low range based)
        price_df = price_df.copy()
        price_df['intraday_range'] = (price_df['high'] - price_df['low']) / price_df['close']
        features['intraday_vol'] = price_df['intraday_range'].iloc[-5:].mean() * 100

        # Overnight gap volatility
        price_df['gap'] = (price_df['open'] - price_df['close'].shift(1)) / price_df['close'].shift(1)
        features['overnight_gap_vol'] = price_df['gap'].iloc[-5:].std() * 100

        return features

    def get_regime_signal_adjustment(self, regime: VolatilityRegime) -> dict:
        """
        Get signal adjustments based on regime.

        Different regimes require different trading approaches.
        """
        adjustments = {
            VolatilityRegime.LOW: {
                'position_size_mult': 0.5,  # Smaller size - low vol = low premium
                'target_mult': 0.75,        # Smaller targets
                'sweep_confidence_req': 0.8, # Need stronger signals
                'reversal_preferred': False, # Trends persist in low vol
                'notes': 'Low vol environment. Reduce size, smaller targets, trend following preferred.'
            },
            VolatilityRegime.MEDIUM: {
                'position_size_mult': 1.0,
                'target_mult': 1.0,
                'sweep_confidence_req': 0.7,
                'reversal_preferred': True,
                'notes': 'Normal trading environment. Standard approach.'
            },
            VolatilityRegime.HIGH: {
                'position_size_mult': 1.5,  # Larger size - high premium
                'target_mult': 1.5,         # Larger targets
                'sweep_confidence_req': 0.6, # Sweeps work well
                'reversal_preferred': True,  # Reversals are strong
                'notes': 'Elevated vol. Good for reversals, larger moves, higher premium.'
            },
            VolatilityRegime.EXTREME: {
                'position_size_mult': 0.75, # Reduce size - too chaotic
                'target_mult': 2.0,         # But targets can be huge
                'sweep_confidence_req': 0.5, # Accept more signals
                'reversal_preferred': True,
                'notes': 'Extreme vol. Reduce size but targets can be massive. Gamma squeezes likely.'
            },
        }

        return adjustments.get(regime, adjustments[VolatilityRegime.MEDIUM])

    def calculate_all_vol_features(self, price_df: pd.DataFrame,
                                    vix_df: Optional[pd.DataFrame] = None) -> dict:
        """
        Calculate all volatility features.

        Args:
            price_df: Price data (SPY/QQQ)
            vix_df: VIX data (optional)

        Returns:
            Combined volatility features
        """
        # Realized vol from prices
        realized_features = self.calculate_realized_vol_features(price_df)

        # VIX features if available
        if vix_df is not None and len(vix_df) > 0:
            vix_features = self.calculate_vix_features(vix_df)
        else:
            # Estimate VIX from realized vol
            estimated_vix = realized_features['realized_vol_20d']
            vix_features = {
                'vix_level': estimated_vix,
                'vix_change_1d': 0,
                'vix_change_5d': 0,
                'vix_percentile_20d': 50,
                'vix_intraday_momentum': 0,
                'vix_term_structure': 0,
                'regime': self.classify_regime(estimated_vix).value,
                'regime_numeric': 1,
            }

        # Combine
        all_features = {**realized_features, **vix_features}

        # Get regime adjustments
        regime = self.classify_regime(all_features['vix_level'])
        adjustments = self.get_regime_signal_adjustment(regime)
        all_features['regime_adjustments'] = adjustments

        return all_features


class NVDACorrelation:
    """
    Use NVDA as tech sector momentum proxy.
    NVDA often leads QQQ moves.
    """

    def __init__(self):
        pass

    def calculate_nvda_features(self, nvda_df: pd.DataFrame, qqq_df: pd.DataFrame) -> dict:
        """
        Calculate NVDA relative strength and divergence features.

        Args:
            nvda_df: NVDA price data
            qqq_df: QQQ price data

        Returns:
            Dictionary of NVDA features
        """
        features = {
            'nvda_relative_strength': 0,
            'nvda_momentum_divergence': 0,
            'nvda_vol_expansion': 0,
            'nvda_leading_indicator': 0,
        }

        if len(nvda_df) < 20 or len(qqq_df) < 20:
            return features

        # Relative strength (NVDA return vs QQQ return)
        nvda_return_5d = (nvda_df['close'].iloc[-1] / nvda_df['close'].iloc[-6] - 1) * 100
        qqq_return_5d = (qqq_df['close'].iloc[-1] / qqq_df['close'].iloc[-6] - 1) * 100

        features['nvda_relative_strength'] = nvda_return_5d - qqq_return_5d

        # Momentum divergence
        nvda_return_1d = (nvda_df['close'].iloc[-1] / nvda_df['close'].iloc[-2] - 1) * 100
        qqq_return_1d = (qqq_df['close'].iloc[-1] / qqq_df['close'].iloc[-2] - 1) * 100

        # Divergence: NVDA moving opposite to QQQ
        if nvda_return_1d * qqq_return_1d < 0:  # Opposite signs
            features['nvda_momentum_divergence'] = abs(nvda_return_1d - qqq_return_1d)

        # NVDA volatility expansion
        nvda_vol_5d = nvda_df['close'].pct_change().iloc[-5:].std()
        nvda_vol_20d = nvda_df['close'].pct_change().iloc[-20:].std()

        if nvda_vol_20d > 0:
            features['nvda_vol_expansion'] = nvda_vol_5d / nvda_vol_20d

        # Leading indicator (does NVDA predict QQQ moves?)
        # Check if NVDA moved first in the last few days
        nvda_direction = np.sign(nvda_return_1d)
        qqq_lagged = (qqq_df['close'].iloc[-2] / qqq_df['close'].iloc[-3] - 1) * 100

        if nvda_direction == np.sign(qqq_return_1d) and nvda_direction != np.sign(qqq_lagged):
            features['nvda_leading_indicator'] = 1  # NVDA led the move

        return features
