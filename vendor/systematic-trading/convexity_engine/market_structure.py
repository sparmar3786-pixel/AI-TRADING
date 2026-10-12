"""
Market Structure Layer
======================
Identifies High Timeframe (HTF) supply/demand zones from Daily, 4H, 1H charts.
These zones act as liquidity magnets and reversal points.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime, timedelta


@dataclass
class Zone:
    """Represents a supply or demand zone."""
    level: float
    zone_type: str  # 'supply' or 'demand'
    timeframe: str  # 'daily', '4h', '1h'
    strength: int  # Number of reactions
    origin_date: datetime
    high: float  # Zone upper bound
    low: float   # Zone lower bound

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2

    @property
    def height(self) -> float:
        return self.high - self.low


class MarketStructure:
    """
    Detects HTF supply/demand zones for institutional reversal points.

    Key levels:
    - Previous day high/low
    - Weekly high/low
    - Large reaction zones
    - Consolidation breakout origins
    """

    def __init__(self):
        self.zones: List[Zone] = []

    def identify_zones(self, df: pd.DataFrame, timeframe: str = 'daily') -> List[Zone]:
        """
        Identify supply and demand zones from OHLCV data.

        Args:
            df: DataFrame with OHLCV data
            timeframe: 'daily', '4h', or '1h'

        Returns:
            List of Zone objects
        """
        zones = []

        # Calculate ATR for zone sizing
        df = df.copy()
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(14).mean()

        # Identify swing highs and lows
        lookback = {'daily': 5, '4h': 8, '1h': 12}.get(timeframe, 5)

        df['swing_high'] = df['high'] == df['high'].rolling(lookback * 2 + 1, center=True).max()
        df['swing_low'] = df['low'] == df['low'].rolling(lookback * 2 + 1, center=True).min()

        # Find demand zones (swing lows with strong rejection)
        for idx in df[df['swing_low']].index:
            if idx not in df.index:
                continue

            row = df.loc[idx]

            # Zone bounds
            zone_low = row['low']
            zone_high = row['low'] + (row['atr'] * 0.5)  # Half ATR zone height

            # Count historical reactions to this level
            reactions = self._count_reactions(df, zone_low, zone_high, 'demand')

            # Calculate rejection strength (wick vs body)
            body = abs(row['close'] - row['open'])
            lower_wick = min(row['open'], row['close']) - row['low']
            rejection_strength = lower_wick / body if body > 0 else 0

            if rejection_strength > 0.5:  # Strong rejection
                zones.append(Zone(
                    level=zone_low,
                    zone_type='demand',
                    timeframe=timeframe,
                    strength=reactions,
                    origin_date=idx,
                    high=zone_high,
                    low=zone_low
                ))

        # Find supply zones (swing highs with strong rejection)
        for idx in df[df['swing_high']].index:
            if idx not in df.index:
                continue

            row = df.loc[idx]

            zone_high = row['high']
            zone_low = row['high'] - (row['atr'] * 0.5)

            reactions = self._count_reactions(df, zone_low, zone_high, 'supply')

            body = abs(row['close'] - row['open'])
            upper_wick = row['high'] - max(row['open'], row['close'])
            rejection_strength = upper_wick / body if body > 0 else 0

            if rejection_strength > 0.5:
                zones.append(Zone(
                    level=zone_high,
                    zone_type='supply',
                    timeframe=timeframe,
                    strength=reactions,
                    origin_date=idx,
                    high=zone_high,
                    low=zone_low
                ))

        self.zones = zones
        return zones

    def _count_reactions(self, df: pd.DataFrame, low: float, high: float, zone_type: str) -> int:
        """Count how many times price reacted to this zone."""
        reactions = 0

        for idx, row in df.iterrows():
            # Check if price touched the zone and reversed
            if zone_type == 'demand':
                if row['low'] <= high and row['close'] > low:
                    reactions += 1
            else:  # supply
                if row['high'] >= low and row['close'] < high:
                    reactions += 1

        return min(reactions, 10)  # Cap at 10

    def get_key_levels(self, df: pd.DataFrame) -> dict:
        """
        Get key structural levels.

        Returns:
            Dictionary with previous day high/low, weekly high/low, etc.
        """
        levels = {}

        # Previous day high/low
        if len(df) >= 2:
            prev_day = df.iloc[-2]
            levels['prev_day_high'] = prev_day['high']
            levels['prev_day_low'] = prev_day['low']

        # Weekly high/low (last 5 trading days)
        if len(df) >= 5:
            weekly = df.iloc[-5:]
            levels['weekly_high'] = weekly['high'].max()
            levels['weekly_low'] = weekly['low'].min()

        # Monthly high/low (last 21 trading days)
        if len(df) >= 21:
            monthly = df.iloc[-21:]
            levels['monthly_high'] = monthly['high'].max()
            levels['monthly_low'] = monthly['low'].min()

        return levels

    def get_nearest_zone(self, price: float, zone_type: Optional[str] = None) -> Optional[Zone]:
        """Get the nearest zone to current price."""
        if not self.zones:
            return None

        filtered = self.zones
        if zone_type:
            filtered = [z for z in self.zones if z.zone_type == zone_type]

        if not filtered:
            return None

        return min(filtered, key=lambda z: abs(z.midpoint - price))

    def calculate_zone_features(self, price: float, atr: float) -> dict:
        """
        Calculate zone-based features for ML model.

        Args:
            price: Current price
            atr: Current ATR

        Returns:
            Dictionary of features
        """
        features = {
            'distance_to_demand': np.nan,
            'distance_to_supply': np.nan,
            'distance_to_demand_atr': np.nan,
            'distance_to_supply_atr': np.nan,
            'nearest_zone_strength': 0,
            'in_demand_zone': 0,
            'in_supply_zone': 0,
            'zone_confluence': 0,
        }

        # Nearest demand zone
        demand = self.get_nearest_zone(price, 'demand')
        if demand:
            features['distance_to_demand'] = price - demand.level
            features['distance_to_demand_atr'] = features['distance_to_demand'] / atr if atr > 0 else 0

            if demand.low <= price <= demand.high:
                features['in_demand_zone'] = 1
                features['nearest_zone_strength'] = demand.strength

        # Nearest supply zone
        supply = self.get_nearest_zone(price, 'supply')
        if supply:
            features['distance_to_supply'] = supply.level - price
            features['distance_to_supply_atr'] = features['distance_to_supply'] / atr if atr > 0 else 0

            if supply.low <= price <= supply.high:
                features['in_supply_zone'] = 1
                features['nearest_zone_strength'] = supply.strength

        # Zone confluence (multiple zones at similar level)
        confluence = 0
        for zone in self.zones:
            if abs(zone.midpoint - price) / atr < 1.0:  # Within 1 ATR
                confluence += 1
        features['zone_confluence'] = confluence

        return features


def resample_to_timeframe(df_1min: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Resample 1-minute data to higher timeframe.

    Args:
        df_1min: 1-minute OHLCV data
        timeframe: '4h' or '1h'

    Returns:
        Resampled DataFrame
    """
    rule = {'1h': '1H', '4h': '4H', 'daily': 'D'}.get(timeframe, '1H')

    resampled = df_1min.resample(rule).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()

    return resampled
