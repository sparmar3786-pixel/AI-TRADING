"""
AURUM Convexity Engine
======================
Main engine combining all components for 0DTE options trading.

Core Philosophy:
- Markets move due to liquidity and dealer hedging
- Edge occurs when liquidity sweeps + overextension + convexity align
- ML refines probabilities, doesn't discover edges randomly
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import os

from .market_structure import MarketStructure, Zone
from .liquidity_sweep import LiquiditySweepDetector, LiquiditySweep
from .overextension import OverextensionDetector
from .convexity_detection import ConvexityDetector
from .dealer_positioning import DealerPositioning, GammaPinDetector
from .volatility_regime import VolatilityRegimeDetector, NVDACorrelation
from .time_effects import TimeOfDayEffects, FridayExpirationEffects
from .ml_models import DailyBiasModel, IntradayConvexityModel
from .regime_detection import MarketRegimeClassifier, MarketRegime, RegimeState


@dataclass
class ConvexitySignal:
    """Represents a trading signal from the engine."""
    timestamp: datetime
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    signal_type: str  # 'SWEEP_REVERSAL', 'OVEREXTENSION', 'GAMMA_SQUEEZE', etc.
    probability: float  # 0-100
    confidence: float  # 0-100
    entry_price: float
    stop_loss: float
    target_1r: float
    target_2r: float

    # Feature scores
    sweep_score: float = 0
    overextension_score: float = 0
    convexity_score: float = 0
    gamma_score: float = 0

    # Context
    regime: str = 'medium'
    session: str = 'normal'
    is_friday: bool = False

    # Expected R multiple
    expected_r: float = 0

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'direction': self.direction,
            'signal_type': self.signal_type,
            'probability': self.probability,
            'confidence': self.confidence,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'target_1r': self.target_1r,
            'target_2r': self.target_2r,
            'sweep_score': self.sweep_score,
            'overextension_score': self.overextension_score,
            'convexity_score': self.convexity_score,
            'gamma_score': self.gamma_score,
            'regime': self.regime,
            'session': self.session,
            'is_friday': self.is_friday,
            'expected_r': self.expected_r,
        }


class ConvexityEngine:
    """
    Main trading engine for 0DTE convexity setups.

    Combines:
    - Market structure (HTF zones)
    - Liquidity sweeps
    - Overextension detection
    - Convexity/acceleration
    - Dealer positioning
    - Volatility regime
    - Time effects

    Outputs high-probability reversal signals for 0DTE options.
    """

    def __init__(self, symbol: str = 'SPY', account_balance: float = 100000):
        self.symbol = symbol
        self.account_balance = account_balance

        # Initialize components
        self.market_structure = MarketStructure()
        self.sweep_detector = LiquiditySweepDetector()
        self.overextension = OverextensionDetector()
        self.convexity = ConvexityDetector()
        self.dealer = DealerPositioning(symbol)
        self.gamma_pin = GammaPinDetector()
        self.vol_regime = VolatilityRegimeDetector()
        self.time_effects = TimeOfDayEffects()
        self.friday_effects = FridayExpirationEffects()

        # ML models
        self.daily_model = DailyBiasModel()
        self.intraday_model = IntradayConvexityModel()

        # Regime detection
        self.regime_classifier = MarketRegimeClassifier(symbol)
        self.current_regime_state: Optional[RegimeState] = None

        # Cache
        self.htf_zones: List[Zone] = []
        self.key_levels: Dict = {}
        self.current_regime = 'medium'
        self.daily_bias = 0
        self.daily_confidence = 50

        # Signal quality thresholds
        self.min_probability = 60  # Only take top signals
        self.min_sweep_score = 50
        self.min_convexity = 40

    def update_htf_context(self, daily_df: pd.DataFrame, h4_df: Optional[pd.DataFrame] = None,
                           h1_df: Optional[pd.DataFrame] = None):
        """
        Update higher timeframe context (call once per day or session).

        Args:
            daily_df: Daily OHLCV data
            h4_df: 4-hour data (optional)
            h1_df: 1-hour data (optional)
        """
        # Identify HTF zones
        daily_zones = self.market_structure.identify_zones(daily_df, 'daily')
        self.htf_zones = daily_zones

        if h4_df is not None:
            h4_zones = self.market_structure.identify_zones(h4_df, '4h')
            self.htf_zones.extend(h4_zones)

        if h1_df is not None:
            h1_zones = self.market_structure.identify_zones(h1_df, '1h')
            self.htf_zones.extend(h1_zones)

        # Get key levels
        self.key_levels = self.market_structure.get_key_levels(daily_df)

        # Update daily bias
        if self.daily_model.is_trained:
            features = self.daily_model.prepare_features(daily_df)
            self.daily_bias, self.daily_confidence = self.daily_model.predict(features.iloc[[-1]])

    def update_volatility_regime(self, vix_df: Optional[pd.DataFrame] = None,
                                  price_df: Optional[pd.DataFrame] = None):
        """
        Update volatility regime classification.
        """
        if vix_df is not None:
            vix_features = self.vol_regime.calculate_vix_features(vix_df)
            self.current_regime = vix_features['regime']
        elif price_df is not None:
            vol_features = self.vol_regime.calculate_realized_vol_features(price_df)
            estimated_vix = vol_features['realized_vol_20d']
            self.current_regime = self.vol_regime.classify_regime(estimated_vix).value

    def analyze_intraday(self, intraday_df: pd.DataFrame, timestamp: datetime) -> Dict:
        """
        Analyze current intraday conditions.

        Args:
            intraday_df: 1-minute or 5-minute OHLCV data
            timestamp: Current timestamp

        Returns:
            Dictionary of all features and scores
        """
        features = {}
        current_price = intraday_df['close'].iloc[-1]

        # 1. Zone features
        atr = self._calculate_atr(intraday_df)
        zone_features = self.market_structure.calculate_zone_features(current_price, atr)
        features.update(zone_features)

        # 2. Liquidity sweep features
        sweep_features = self.sweep_detector.calculate_sweep_features(intraday_df, self.key_levels)
        features.update(sweep_features)

        # 3. Overextension features
        overext_features = self.overextension.calculate_overextension_features(intraday_df)
        features.update(overext_features)

        # 4. Convexity features
        convexity_features = self.convexity.calculate_acceleration_features(intraday_df)
        features.update(convexity_features)

        # 5. Dealer positioning features
        dealer_features = self.dealer.calculate_all_dealer_features(current_price, timestamp)
        features.update(dealer_features)

        # 6. Gamma pin features
        pin_features = self.gamma_pin.calculate_pin_features(intraday_df, current_price, timestamp)
        features.update(pin_features)

        # 7. Time features
        time_features = self.time_effects.calculate_time_features(timestamp)
        features.update(time_features)

        # 8. Friday features
        friday_features = self.friday_effects.calculate_friday_features(timestamp, current_price)
        features.update(friday_features)

        # 9. Regime
        features['regime'] = self.current_regime
        features['regime_numeric'] = {'low': 0, 'medium': 1, 'high': 2, 'extreme': 3}.get(self.current_regime, 1)

        # 10. Daily bias
        features['daily_bias'] = self.daily_bias
        features['daily_confidence'] = self.daily_confidence

        # 11. Regime detection
        self.current_regime_state = self.regime_classifier.classify_regime(intraday_df, timestamp)
        features['market_regime'] = self.current_regime_state.regime.value
        features['trend_day_probability'] = self.current_regime_state.trend_day_probability
        features['gamma_expansion_probability'] = self.current_regime_state.gamma_expansion_probability

        return features

    def generate_signal(self, intraday_df: pd.DataFrame, timestamp: datetime) -> Optional[ConvexitySignal]:
        """
        Generate trading signal if conditions align.

        This is the main entry point for signal generation.

        Args:
            intraday_df: Intraday price data
            timestamp: Current timestamp

        Returns:
            ConvexitySignal or None
        """
        # Get all features
        features = self.analyze_intraday(intraday_df, timestamp)
        current_price = intraday_df['close'].iloc[-1]

        # Time filter
        time_adj = self.time_effects.get_signal_adjustment(timestamp)
        if not time_adj['should_trade']:
            return None

        # Get ML probability
        probability, ml_details = self.intraday_model.predict_reversal_probability(features)

        # Apply time adjustment
        probability += time_adj['confidence_adjustment'] * -10

        # Apply regime-based adjustments
        if self.current_regime_state:
            regime_adaptation = self.regime_classifier.get_strategy_adaptation(self.current_regime_state)

            # In trend day or gamma regime, reduce probability for counter-trend
            if self.current_regime_state.regime in [MarketRegime.TREND_DAY, MarketRegime.GAMMA_EXPANSION]:
                # Check if signal would be counter-trend
                trend_direction = 1 if features.get('distance_from_vwap', 0) > 0 else -1
                signal_type, signal_dir = self._determine_signal_type(features)
                if signal_dir:
                    signal_direction = 1 if signal_dir == 'LONG' else -1
                    if signal_direction != trend_direction:
                        probability *= 0.5  # Halve probability for counter-trend in trending regimes

        # Check minimum probability
        if probability < self.min_probability:
            return None

        # Determine signal type and direction
        signal_type, direction = self._determine_signal_type(features)
        if signal_type is None:
            return None

        # Check direction alignment with daily bias
        if self.daily_confidence > 70:
            if (self.daily_bias == 1 and direction == 'SHORT') or \
               (self.daily_bias == -1 and direction == 'LONG'):
                probability *= 0.8  # Reduce confidence if against daily bias

        # Calculate stops and targets with regime adaptation
        atr = self._calculate_atr(intraday_df)

        # Get regime multipliers
        stop_mult = 1.0
        target_mult = 1.0
        if self.current_regime_state:
            adaptation = self.regime_classifier.get_strategy_adaptation(self.current_regime_state)
            stop_mult = adaptation.get('stop_mult', 1.0)
            target_mult = adaptation.get('target_mult', 1.0)

        stop_loss, target_1r, target_2r = self._calculate_levels(
            current_price, direction, atr, features, stop_mult, target_mult
        )

        # Calculate expected R
        expected_r = self._calculate_expected_r(probability)

        # Build signal
        signal = ConvexitySignal(
            timestamp=timestamp,
            symbol=self.symbol,
            direction=direction,
            signal_type=signal_type,
            probability=probability,
            confidence=self.daily_confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            target_1r=target_1r,
            target_2r=target_2r,
            sweep_score=features.get('sweep_detected', 0) * 100,
            overextension_score=features.get('exhaustion_score', 0),
            convexity_score=features.get('convexity_score', 0),
            gamma_score=features.get('gamma_proximity_score', 0),
            regime=self.current_regime,
            session=features.get('session', 'normal'),
            is_friday=features.get('is_friday', 0) == 1,
            expected_r=expected_r,
        )

        return signal

    def _determine_signal_type(self, features: dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Determine signal type and direction from features.
        """
        # Priority 1: Liquidity sweep
        if features.get('sweep_detected', 0) == 1:
            direction = 'LONG' if features.get('sweep_direction', 0) == 1 else 'SHORT'
            return 'SWEEP_REVERSAL', direction

        # Priority 2: Overextension reversal
        if features.get('exhaustion_score', 0) > 70:
            if features.get('vwap_zscore', 0) > 2:
                return 'OVEREXTENSION', 'SHORT'
            elif features.get('vwap_zscore', 0) < -2:
                return 'OVEREXTENSION', 'LONG'

        # Priority 3: Gamma squeeze
        if features.get('gamma_squeeze_potential', 0) > 70:
            if features.get('3min_return', 0) > 0.2:
                return 'GAMMA_SQUEEZE', 'LONG'
            elif features.get('3min_return', 0) < -0.2:
                return 'GAMMA_SQUEEZE', 'SHORT'

        # Priority 4: Convexity burst
        if features.get('convexity_score', 0) > 60:
            if features.get('price_acceleration', 0) > 0:
                return 'CONVEXITY_BURST', 'LONG'
            else:
                return 'CONVEXITY_BURST', 'SHORT'

        # Priority 5: Zone touch
        if features.get('in_demand_zone', 0) == 1:
            return 'ZONE_TOUCH', 'LONG'
        if features.get('in_supply_zone', 0) == 1:
            return 'ZONE_TOUCH', 'SHORT'

        return None, None

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR."""
        tr = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        return tr.rolling(period).mean().iloc[-1]

    def _calculate_levels(self, price: float, direction: str, atr: float,
                          features: dict, stop_mult: float = 1.0,
                          target_mult: float = 1.0) -> Tuple[float, float, float]:
        """
        Calculate stop loss and targets.

        For 0DTE, we use tighter stops (0.3-0.5 ATR).
        Regime adaptation adjusts these multipliers.
        """
        # Base stop ATR (tighter for 0DTE - the edge is tight stops)
        base_stop_atr = 0.3 if features.get('is_power_hour', 0) else 0.5

        # Apply regime multiplier
        stop_atr = base_stop_atr * stop_mult

        if direction == 'LONG':
            stop_loss = price - (stop_atr * atr)
            risk = price - stop_loss
            target_1r = price + (risk * target_mult)
            target_2r = price + (2 * risk * target_mult)
        else:
            stop_loss = price + (stop_atr * atr)
            risk = stop_loss - price
            target_1r = price - (risk * target_mult)
            target_2r = price - (2 * risk * target_mult)

        return stop_loss, target_1r, target_2r

    def _calculate_expected_r(self, probability: float) -> float:
        """
        Calculate expected R multiple.

        Expected R = (win_rate * avg_win) - (loss_rate * avg_loss)
        """
        win_rate = probability / 100
        loss_rate = 1 - win_rate

        # Assume 2R target, 1R stop
        avg_win = 2.0
        avg_loss = 1.0

        expected_r = (win_rate * avg_win) - (loss_rate * avg_loss)
        return expected_r

    def get_position_size(self, signal: ConvexitySignal, risk_pct: float = 0.01) -> dict:
        """
        Calculate position size for a signal.

        Args:
            signal: The trading signal
            risk_pct: Risk per trade as decimal (0.01 = 1%)

        Returns:
            Position sizing details
        """
        risk_amount = self.account_balance * risk_pct

        # Risk per share/contract
        risk_per_unit = abs(signal.entry_price - signal.stop_loss)

        # Shares (for underlying)
        shares = int(risk_amount / risk_per_unit) if risk_per_unit > 0 else 0

        # For options: rough estimate of contracts
        # Assuming ATM options with ~0.5 delta
        option_premium_estimate = risk_per_unit * 0.5  # Very rough
        contracts = int(risk_amount / (option_premium_estimate * 100)) if option_premium_estimate > 0 else 1

        return {
            'risk_amount': risk_amount,
            'risk_per_unit': risk_per_unit,
            'shares': shares,
            'estimated_contracts': max(1, contracts),
            'position_value': shares * signal.entry_price,
        }

    def print_analysis(self, features: dict):
        """Print analysis summary."""
        print("\n" + "=" * 60)
        print("CONVEXITY ENGINE ANALYSIS")
        print("=" * 60)

        print(f"\nMarket Regime: {features.get('market_regime', 'mean_reversion').upper()}")
        print(f"  Trend Day Prob: {features.get('trend_day_probability', 0):.1f}%")
        print(f"  Gamma Expansion Prob: {features.get('gamma_expansion_probability', 0):.1f}%")

        print(f"\nVolatility Regime: {features.get('regime', 'unknown').upper()}")
        print(f"Session: {features.get('session', 'unknown')}")
        print(f"Daily Bias: {'BULLISH' if features.get('daily_bias', 0) > 0 else 'BEARISH' if features.get('daily_bias', 0) < 0 else 'NEUTRAL'}")

        print(f"\nSweep Detected: {'YES' if features.get('sweep_detected', 0) else 'NO'}")
        print(f"  Wick Ratio: {features.get('wick_ratio', 0):.2f}")
        print(f"  Volume Spike: {features.get('volume_at_sweep', 0):.2f}x")

        print(f"\nOverextension:")
        print(f"  VWAP Z-Score: {features.get('vwap_zscore', 0):.2f}")
        print(f"  Exhaustion Score: {features.get('exhaustion_score', 0):.1f}")
        print(f"  RSI: {features.get('rsi_14', 50):.1f}")

        print(f"\nConvexity:")
        print(f"  Acceleration Z: {features.get('price_acceleration_zscore', 0):.2f}")
        print(f"  Convexity Score: {features.get('convexity_score', 0):.1f}")
        print(f"  Momentum Burst: {features.get('momentum_burst_score', 0):.1f}%")

        print(f"\nGamma/Dealer:")
        print(f"  Gamma Proximity: {features.get('gamma_proximity_score', 0):.1f}")
        print(f"  Distance to Round Strike: ${features.get('distance_to_round_strike', 0):.2f}")
        print(f"  Pin Risk: {features.get('pin_risk', 0):.1f}%")

        print("=" * 60)
