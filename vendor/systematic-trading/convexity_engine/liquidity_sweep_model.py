"""
Liquidity Sweep Detection Model
================================
Identifies when price briefly moves beyond a key level to trigger stops,
then quickly reverses - a high-probability reversal trigger.

This is Layer 4 of the professional systematic desk architecture:
  Layer 1: Market Context (supply/demand regime)
  Layer 2: Intraday Regime (trend day vs mean reversion)
  Layer 3: Gamma Dynamics (dealer hedging)
  Layer 4: Liquidity Events (stop hunts / sweeps) <-- THIS
  Layer 5: Execution (5-minute trade model)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class SweepDirection(Enum):
    """Direction of the liquidity sweep."""
    BUY_SIDE = "buy_side"   # Broke above resistance, reverses down (short setup)
    SELL_SIDE = "sell_side"  # Broke below support, reverses up (long setup)


class LevelType(Enum):
    """Type of liquidity level."""
    PREV_DAY_HIGH = "prev_day_high"
    PREV_DAY_LOW = "prev_day_low"
    PREV_DAY_CLOSE = "prev_day_close"
    INTRADAY_SWING_HIGH = "intraday_swing_high"
    INTRADAY_SWING_LOW = "intraday_swing_low"
    OPENING_RANGE_HIGH = "or_high"
    OPENING_RANGE_LOW = "or_low"
    SUPPLY_ZONE = "supply_zone"
    DEMAND_ZONE = "demand_zone"
    VWAP_UPPER = "vwap_upper"
    VWAP_LOWER = "vwap_lower"
    ROUND_NUMBER = "round_number"


@dataclass
class LiquidityLevel:
    """Represents a liquidity level where stops cluster."""
    price: float
    level_type: LevelType
    strength: float  # 0-1, how significant is this level
    last_touch: Optional[datetime] = None
    touch_count: int = 0


@dataclass
class SweepSignal:
    """Represents a detected liquidity sweep."""
    timestamp: datetime
    direction: SweepDirection
    level: LiquidityLevel
    sweep_probability: float
    sweep_strength: float
    entry_price: float
    stop_price: float
    target_price: float

    # Component scores
    wick_ratio: float
    velocity_spike: float
    reversal_speed: float
    volume_spike: float

    # Context
    confirmed: bool

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'direction': self.direction.value,
            'level_type': self.level.level_type.value,
            'level_price': self.level.price,
            'sweep_probability': self.sweep_probability,
            'sweep_strength': self.sweep_strength,
            'entry_price': self.entry_price,
            'stop_price': self.stop_price,
            'target_price': self.target_price,
            'wick_ratio': self.wick_ratio,
            'velocity_spike': self.velocity_spike,
            'confirmed': self.confirmed,
        }


# =============================================================================
# PART 1: LIQUIDITY LEVEL IDENTIFICATION
# =============================================================================

class LiquidityLevelIdentifier:
    """
    Identifies key liquidity levels where stops cluster.

    Levels include:
    - Previous session levels (high/low/close)
    - Intraday swing points
    - Opening range
    - Supply/demand zones
    - VWAP bands
    - Round numbers
    """

    def __init__(self):
        self.levels: List[LiquidityLevel] = []

    def identify_all_levels(self, daily_df: pd.DataFrame, intraday_df: pd.DataFrame,
                            supply_zones: List[float] = None,
                            demand_zones: List[float] = None) -> List[LiquidityLevel]:
        """
        Identify all liquidity levels from available data.

        Args:
            daily_df: Daily OHLCV data
            intraday_df: Intraday OHLCV data
            supply_zones: List of supply zone prices
            demand_zones: List of demand zone prices

        Returns:
            List of LiquidityLevel objects
        """
        self.levels = []

        # Previous session levels
        self._add_previous_session_levels(daily_df)

        # Intraday levels
        self._add_intraday_swing_levels(intraday_df)
        self._add_opening_range_levels(intraday_df)

        # Market structure levels
        if supply_zones:
            for zone in supply_zones:
                self.levels.append(LiquidityLevel(
                    price=zone,
                    level_type=LevelType.SUPPLY_ZONE,
                    strength=0.8
                ))

        if demand_zones:
            for zone in demand_zones:
                self.levels.append(LiquidityLevel(
                    price=zone,
                    level_type=LevelType.DEMAND_ZONE,
                    strength=0.8
                ))

        # VWAP bands
        self._add_vwap_levels(intraday_df)

        # Round numbers
        if len(intraday_df) > 0:
            current_price = intraday_df['close'].iloc[-1]
            self._add_round_number_levels(current_price)

        return self.levels

    def _add_previous_session_levels(self, daily_df: pd.DataFrame):
        """Add previous day high/low/close levels."""
        if daily_df is None or len(daily_df) < 2:
            return

        prev_day = daily_df.iloc[-2]

        self.levels.append(LiquidityLevel(
            price=prev_day['high'],
            level_type=LevelType.PREV_DAY_HIGH,
            strength=0.9  # Very significant
        ))

        self.levels.append(LiquidityLevel(
            price=prev_day['low'],
            level_type=LevelType.PREV_DAY_LOW,
            strength=0.9
        ))

        self.levels.append(LiquidityLevel(
            price=prev_day['close'],
            level_type=LevelType.PREV_DAY_CLOSE,
            strength=0.6
        ))

    def _add_intraday_swing_levels(self, intraday_df: pd.DataFrame, lookback: int = 50):
        """Add intraday swing high/low levels."""
        if intraday_df is None or len(intraday_df) < lookback:
            return

        recent = intraday_df.iloc[-lookback:]

        # Find swing highs (local maxima)
        for i in range(5, len(recent) - 5):
            if recent['high'].iloc[i] == recent['high'].iloc[i-5:i+6].max():
                self.levels.append(LiquidityLevel(
                    price=recent['high'].iloc[i],
                    level_type=LevelType.INTRADAY_SWING_HIGH,
                    strength=0.7,
                    last_touch=recent.index[i] if hasattr(recent.index[i], 'isoformat') else None
                ))

        # Find swing lows (local minima)
        for i in range(5, len(recent) - 5):
            if recent['low'].iloc[i] == recent['low'].iloc[i-5:i+6].min():
                self.levels.append(LiquidityLevel(
                    price=recent['low'].iloc[i],
                    level_type=LevelType.INTRADAY_SWING_LOW,
                    strength=0.7,
                    last_touch=recent.index[i] if hasattr(recent.index[i], 'isoformat') else None
                ))

    def _add_opening_range_levels(self, intraday_df: pd.DataFrame, or_minutes: int = 30):
        """Add opening range high/low levels."""
        if intraday_df is None or len(intraday_df) < 10:
            return

        try:
            # Get today's data
            today = intraday_df.index[-1].date() if hasattr(intraday_df.index[-1], 'date') else None
            if today is None:
                return

            today_data = intraday_df[intraday_df.index.date == today]
            if len(today_data) < 6:  # Need at least 30 min of data
                return

            # Opening range (first 30 minutes = first 6 bars at 5-min)
            or_bars = min(6, len(today_data))
            or_data = today_data.iloc[:or_bars]

            or_high = or_data['high'].max()
            or_low = or_data['low'].min()

            self.levels.append(LiquidityLevel(
                price=or_high,
                level_type=LevelType.OPENING_RANGE_HIGH,
                strength=0.85
            ))

            self.levels.append(LiquidityLevel(
                price=or_low,
                level_type=LevelType.OPENING_RANGE_LOW,
                strength=0.85
            ))
        except:
            pass

    def _add_vwap_levels(self, intraday_df: pd.DataFrame, std_mult: float = 2.0):
        """Add VWAP +/- 2 standard deviation levels."""
        if intraday_df is None or len(intraday_df) < 20:
            return

        df = intraday_df.copy()

        # Calculate VWAP
        df['typical'] = (df['high'] + df['low'] + df['close']) / 3

        if 'volume' in df.columns and df['volume'].sum() > 0:
            df['cum_vol'] = df['volume'].cumsum()
            df['cum_val'] = (df['typical'] * df['volume']).cumsum()
            df['vwap'] = df['cum_val'] / df['cum_vol']
        else:
            df['vwap'] = df['typical'].expanding().mean()

        # Calculate standard deviation
        df['squared_diff'] = (df['typical'] - df['vwap']) ** 2
        df['cum_squared_diff'] = df['squared_diff'].cumsum()
        df['cum_count'] = range(1, len(df) + 1)
        df['std'] = np.sqrt(df['cum_squared_diff'] / df['cum_count'])

        current_vwap = df['vwap'].iloc[-1]
        current_std = df['std'].iloc[-1]

        if not np.isnan(current_vwap) and not np.isnan(current_std):
            self.levels.append(LiquidityLevel(
                price=current_vwap + (std_mult * current_std),
                level_type=LevelType.VWAP_UPPER,
                strength=0.65
            ))

            self.levels.append(LiquidityLevel(
                price=current_vwap - (std_mult * current_std),
                level_type=LevelType.VWAP_LOWER,
                strength=0.65
            ))

    def _add_round_number_levels(self, current_price: float, range_pct: float = 0.01):
        """Add psychological round number levels."""
        # Find nearest round numbers
        base = round(current_price / 5) * 5  # $5 intervals for SPY

        for offset in [-10, -5, 0, 5, 10]:
            level = base + offset
            # Only add if within range of current price
            if abs(level - current_price) / current_price < range_pct:
                self.levels.append(LiquidityLevel(
                    price=level,
                    level_type=LevelType.ROUND_NUMBER,
                    strength=0.5
                ))

    def get_nearest_level(self, price: float, direction: str = None) -> Optional[LiquidityLevel]:
        """Get the nearest liquidity level to current price."""
        if not self.levels:
            return None

        if direction == 'above':
            above_levels = [l for l in self.levels if l.price > price]
            if above_levels:
                return min(above_levels, key=lambda l: l.price - price)
        elif direction == 'below':
            below_levels = [l for l in self.levels if l.price < price]
            if below_levels:
                return max(below_levels, key=lambda l: l.price)
        else:
            return min(self.levels, key=lambda l: abs(l.price - price))

        return None

    def get_levels_in_range(self, price: float, atr: float, multiplier: float = 1.0) -> List[LiquidityLevel]:
        """Get all levels within ATR range of price."""
        range_dist = atr * multiplier
        return [l for l in self.levels if abs(l.price - price) <= range_dist]


# =============================================================================
# PART 2-6: SWEEP DETECTION & SCORING
# =============================================================================

class LiquiditySweepDetector:
    """
    Detects liquidity sweeps - false breakouts driven by stop hunts.

    A sweep occurs when:
    1. Price breaks a known liquidity level
    2. Break distance is small (stop-hunt, not real breakout)
    3. Price quickly reverses
    4. Strong rejection wick forms
    """

    def __init__(self):
        self.level_identifier = LiquidityLevelIdentifier()

        # Thresholds
        self.break_threshold_atr = 0.3  # Max break distance in ATR
        self.confirmation_bars = 3  # Bars to confirm reversal
        self.min_wick_ratio = 1.5  # Minimum wick/body ratio

        # Scoring weights
        self.weights = {
            'wick_ratio': 0.25,
            'velocity_spike': 0.20,
            'reversal_speed': 0.20,
            'distance_score': 0.20,
            'volume_spike': 0.15,
        }

    def detect_sweep(self, intraday_df: pd.DataFrame, daily_df: pd.DataFrame = None,
                     supply_zones: List[float] = None, demand_zones: List[float] = None,
                     timestamp: datetime = None) -> Optional[SweepSignal]:
        """
        Detect if current bar shows a liquidity sweep.

        Args:
            intraday_df: Intraday OHLCV data
            daily_df: Daily data for context
            supply_zones: Supply zone prices
            demand_zones: Demand zone prices
            timestamp: Current timestamp

        Returns:
            SweepSignal if sweep detected, None otherwise
        """
        if len(intraday_df) < 20:
            return None

        # Identify liquidity levels
        levels = self.level_identifier.identify_all_levels(
            daily_df, intraday_df, supply_zones, demand_zones
        )

        if not levels:
            return None

        # Get current bar and recent data
        current = intraday_df.iloc[-1]
        recent = intraday_df.iloc[-20:]

        # Calculate ATR
        atr = self._calculate_atr(intraday_df)

        # Check each level for sweep
        for level in levels:
            sweep = self._check_level_sweep(current, recent, level, atr, timestamp)
            if sweep:
                return sweep

        return None

    def _check_level_sweep(self, current: pd.Series, recent: pd.DataFrame,
                           level: LiquidityLevel, atr: float,
                           timestamp: datetime) -> Optional[SweepSignal]:
        """Check if current bar sweeps a specific level."""

        price = current['close']
        high = current['high']
        low = current['low']
        open_price = current['open']

        # Calculate candle metrics
        candle_range = high - low
        body = abs(price - open_price)
        upper_wick = high - max(price, open_price)
        lower_wick = min(price, open_price) - low

        # Check for BUY-SIDE sweep (broke above, reverses down)
        if high > level.price and price < level.price:
            break_distance = high - level.price

            # Check if break is small enough (not real breakout)
            if break_distance < atr * self.break_threshold_atr:
                # Calculate rejection metrics
                wick_ratio = upper_wick / body if body > 0 else 10

                if wick_ratio >= self.min_wick_ratio:
                    # Calculate all component scores
                    scores = self._calculate_sweep_scores(
                        current, recent, level, atr, 'buy_side'
                    )

                    # Calculate overall probability
                    probability = self._calculate_sweep_probability(scores)

                    if probability > 50:  # Minimum threshold
                        # Calculate trade levels
                        entry = price
                        stop = high + (0.2 * atr)  # Stop above sweep high
                        target = price - (2 * (stop - entry))  # 2R target

                        return SweepSignal(
                            timestamp=timestamp,
                            direction=SweepDirection.BUY_SIDE,
                            level=level,
                            sweep_probability=probability,
                            sweep_strength=scores['strength'],
                            entry_price=entry,
                            stop_price=stop,
                            target_price=target,
                            wick_ratio=wick_ratio,
                            velocity_spike=scores['velocity_spike'],
                            reversal_speed=scores['reversal_speed'],
                            volume_spike=scores['volume_spike'],
                            confirmed=scores['confirmed']
                        )

        # Check for SELL-SIDE sweep (broke below, reverses up)
        if low < level.price and price > level.price:
            break_distance = level.price - low

            if break_distance < atr * self.break_threshold_atr:
                wick_ratio = lower_wick / body if body > 0 else 10

                if wick_ratio >= self.min_wick_ratio:
                    scores = self._calculate_sweep_scores(
                        current, recent, level, atr, 'sell_side'
                    )

                    probability = self._calculate_sweep_probability(scores)

                    if probability > 50:
                        entry = price
                        stop = low - (0.2 * atr)
                        target = price + (2 * (entry - stop))

                        return SweepSignal(
                            timestamp=timestamp,
                            direction=SweepDirection.SELL_SIDE,
                            level=level,
                            sweep_probability=probability,
                            sweep_strength=scores['strength'],
                            entry_price=entry,
                            stop_price=stop,
                            target_price=target,
                            wick_ratio=wick_ratio,
                            velocity_spike=scores['velocity_spike'],
                            reversal_speed=scores['reversal_speed'],
                            volume_spike=scores['volume_spike'],
                            confirmed=scores['confirmed']
                        )

        return None

    def _calculate_sweep_scores(self, current: pd.Series, recent: pd.DataFrame,
                                level: LiquidityLevel, atr: float,
                                direction: str) -> dict:
        """Calculate all component scores for sweep detection."""
        scores = {
            'wick_ratio_score': 0,
            'velocity_spike': 0,
            'reversal_speed': 0,
            'distance_score': 0,
            'volume_spike': 0,
            'strength': 0,
            'confirmed': False,
        }

        # Wick ratio score
        high = current['high']
        low = current['low']
        body = abs(current['close'] - current['open'])
        candle_range = high - low

        if direction == 'buy_side':
            wick = high - max(current['close'], current['open'])
        else:
            wick = min(current['close'], current['open']) - low

        wick_ratio = wick / body if body > 0 else 10
        scores['wick_ratio_score'] = min(wick_ratio / 3, 1) * 100  # Normalize to 0-100

        # Velocity spike (price moved fast before sweep)
        if len(recent) >= 4:
            move_3bar = abs(recent['close'].iloc[-4] - recent['close'].iloc[-1])
            avg_3bar_range = (recent['high'] - recent['low']).iloc[-10:-1].mean() * 3
            if avg_3bar_range > 0:
                scores['velocity_spike'] = min(move_3bar / avg_3bar_range, 2) * 50

        # Reversal speed (how fast did it come back)
        if direction == 'buy_side':
            reversal_dist = high - current['close']
            sweep_dist = high - level.price
        else:
            reversal_dist = current['close'] - low
            sweep_dist = level.price - low

        if sweep_dist > 0:
            scores['reversal_speed'] = min(reversal_dist / sweep_dist, 2) * 50

        # Distance score (smaller break = more likely sweep)
        if direction == 'buy_side':
            break_dist = high - level.price
        else:
            break_dist = level.price - low

        dist_ratio = break_dist / atr if atr > 0 else 1
        scores['distance_score'] = max(0, (1 - dist_ratio / self.break_threshold_atr)) * 100

        # Volume spike (if available)
        if 'volume' in recent.columns:
            current_vol = current.get('volume', 0)
            avg_vol = recent['volume'].iloc[-20:].mean()
            if avg_vol > 0:
                scores['volume_spike'] = min(current_vol / avg_vol, 3) * 33
        else:
            scores['volume_spike'] = 50  # Neutral if no volume

        # Overall strength
        scores['strength'] = (
            scores['wick_ratio_score'] * 0.3 +
            scores['velocity_spike'] * 0.2 +
            scores['reversal_speed'] * 0.3 +
            scores['distance_score'] * 0.2
        )

        # Confirmation (price stayed on reversal side)
        if direction == 'buy_side':
            scores['confirmed'] = current['close'] < level.price
        else:
            scores['confirmed'] = current['close'] > level.price

        return scores

    def _calculate_sweep_probability(self, scores: dict) -> float:
        """Calculate overall sweep probability from component scores."""
        probability = (
            self.weights['wick_ratio'] * scores['wick_ratio_score'] +
            self.weights['velocity_spike'] * scores['velocity_spike'] +
            self.weights['reversal_speed'] * scores['reversal_speed'] +
            self.weights['distance_score'] * scores['distance_score'] +
            self.weights['volume_spike'] * scores['volume_spike']
        )

        # Boost if confirmed
        if scores['confirmed']:
            probability *= 1.2

        return min(probability, 100)

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR."""
        if len(df) < period:
            return (df['high'] - df['low']).mean()

        tr = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        return tr.rolling(period).mean().iloc[-1]

    def calculate_sweep_features(self, intraday_df: pd.DataFrame, daily_df: pd.DataFrame = None,
                                  timestamp: datetime = None) -> dict:
        """
        Calculate sweep-related features for ML model.

        Returns dict of features that can be used by the trading model.
        """
        features = {
            'liquidity_sweep_probability': 0,
            'sweep_direction': 0,  # 1 = sell-side (long), -1 = buy-side (short), 0 = none
            'sweep_level_type': 'none',
            'sweep_strength': 0,
            'nearest_level_distance': 0,
            'levels_nearby': 0,
            'wick_ratio': 0,
            'velocity_spike': 0,
        }

        if len(intraday_df) < 20:
            return features

        # Identify levels
        levels = self.level_identifier.identify_all_levels(daily_df, intraday_df)

        current_price = intraday_df['close'].iloc[-1]
        atr = self._calculate_atr(intraday_df)

        # Count nearby levels
        if atr > 0:
            features['levels_nearby'] = len([
                l for l in levels if abs(l.price - current_price) < atr
            ])

        # Get nearest level
        nearest = self.level_identifier.get_nearest_level(current_price)
        if nearest and atr > 0:
            features['nearest_level_distance'] = abs(nearest.price - current_price) / atr

        # Detect sweep
        sweep = self.detect_sweep(intraday_df, daily_df, timestamp=timestamp)

        if sweep:
            features['liquidity_sweep_probability'] = sweep.sweep_probability
            features['sweep_direction'] = 1 if sweep.direction == SweepDirection.SELL_SIDE else -1
            features['sweep_level_type'] = sweep.level.level_type.value
            features['sweep_strength'] = sweep.sweep_strength
            features['wick_ratio'] = sweep.wick_ratio
            features['velocity_spike'] = sweep.velocity_spike

        return features


# =============================================================================
# PART 8-9: INTEGRATION WITH TRADING SYSTEM
# =============================================================================

class SweepTradingIntegration:
    """
    Integrates sweep signals with the trading system.

    Uses regime classifier to filter signals:
    - In mean_reversion regime: Use sweep signals for reversals
    - In trend_day/gamma_expansion: Ignore sweep signals (don't fade)
    """

    def __init__(self):
        self.sweep_detector = LiquiditySweepDetector()
        self.min_probability = 65  # Minimum sweep probability to act

    def should_trade_sweep(self, sweep: SweepSignal, market_regime: str) -> Tuple[bool, str]:
        """
        Determine if sweep signal should be traded based on regime.

        Args:
            sweep: Detected sweep signal
            market_regime: Current market regime

        Returns:
            Tuple of (should_trade, reason)
        """
        # Don't fade moves in trending/gamma regimes
        if market_regime in ['trend_day', 'gamma_expansion']:
            return False, f"Regime is {market_regime} - don't fade sweeps"

        # Check probability threshold
        if sweep.sweep_probability < self.min_probability:
            return False, f"Probability {sweep.sweep_probability:.0f}% below threshold"

        # Check if confirmed
        if not sweep.confirmed:
            return False, "Sweep not confirmed (price didn't hold reversal)"

        return True, "Sweep signal valid in mean_reversion regime"

    def get_trade_from_sweep(self, sweep: SweepSignal, account_balance: float = 100000,
                             risk_pct: float = 0.01) -> dict:
        """
        Convert sweep signal to trade parameters.

        Args:
            sweep: Sweep signal
            account_balance: Account balance
            risk_pct: Risk per trade

        Returns:
            Trade parameters dict
        """
        risk_amount = account_balance * risk_pct

        # Calculate position size
        risk_per_share = abs(sweep.entry_price - sweep.stop_price)
        shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

        # Direction
        if sweep.direction == SweepDirection.SELL_SIDE:
            direction = 'LONG'
        else:
            direction = 'SHORT'

        return {
            'direction': direction,
            'entry': sweep.entry_price,
            'stop_loss': sweep.stop_price,
            'target': sweep.target_price,
            'shares': shares,
            'risk_amount': risk_amount,
            'signal_type': 'LIQUIDITY_SWEEP',
            'level_type': sweep.level.level_type.value,
            'sweep_probability': sweep.sweep_probability,
            'sweep_strength': sweep.sweep_strength,
            'confidence': sweep.sweep_probability / 100,
        }

    def print_sweep_signal(self, sweep: SweepSignal, trade: dict = None):
        """Print sweep signal details."""
        direction_color = "\033[92m" if sweep.direction == SweepDirection.SELL_SIDE else "\033[91m"
        reset = "\033[0m"

        print()
        print("!" * 60)
        print("!           LIQUIDITY SWEEP DETECTED")
        print("!" * 60)
        print()
        print(f"  Sweep Type:    {direction_color}{sweep.direction.value.upper()}{reset}")
        print(f"  Level Type:    {sweep.level.level_type.value}")
        print(f"  Level Price:   ${sweep.level.price:.2f}")
        print()
        print(f"  Probability:   {sweep.sweep_probability:.0f}%")
        print(f"  Strength:      {sweep.sweep_strength:.0f}")
        print(f"  Confirmed:     {'YES' if sweep.confirmed else 'NO'}")
        print()
        print(f"  Component Scores:")
        print(f"    Wick Ratio:    {sweep.wick_ratio:.2f}")
        print(f"    Velocity:      {sweep.velocity_spike:.0f}")
        print(f"    Reversal:      {sweep.reversal_speed:.0f}")

        if trade:
            print()
            print(f"  Trade Setup:")
            print(f"    Direction:   {trade['direction']}")
            print(f"    Entry:       ${trade['entry']:.2f}")
            print(f"    Stop:        ${trade['stop_loss']:.2f}")
            print(f"    Target:      ${trade['target']:.2f}")
            print(f"    Shares:      {trade['shares']}")

        print("!" * 60)
