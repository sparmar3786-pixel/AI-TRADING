"""
0DTE Trading System - Zone Detection Module
============================================
Automatically detects supply and demand zones using:
  - Marubozu candles (strong momentum candles)
  - Wick extremes (rejection zones)
  - High volume areas (institutional activity)
  - Historical reversal success rates

Zone Types:
  - DEMAND: Areas where price previously reversed upward (buying pressure)
  - SUPPLY: Areas where price previously reversed downward (selling pressure)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class ZoneType(Enum):
    DEMAND = "demand"  # Buying zone (support)
    SUPPLY = "supply"  # Selling zone (resistance)


class ZoneStrength(Enum):
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    EXTREME = 4


@dataclass
class Zone:
    """
    Represents a supply or demand zone.

    The zone has:
    - Upper and lower bounds
    - Midpoint for precise entries
    - Strength score based on formation
    - Historical touch count and reversal success
    """
    zone_type: ZoneType
    upper: float
    lower: float
    formation_time: pd.Timestamp
    formation_idx: int

    # Zone metrics
    strength: ZoneStrength = ZoneStrength.MODERATE
    volume_profile: float = 1.0  # Relative volume at formation
    body_ratio: float = 0.0  # Body/range ratio of forming candle
    wick_rejection: float = 0.0  # Wick size indicating rejection

    # Historical performance
    touch_count: int = 0
    successful_reversals: int = 0
    failed_breaks: int = 0

    # Flags
    is_fresh: bool = True  # Never been tested
    is_valid: bool = True  # Still tradeable

    @property
    def midpoint(self) -> float:
        """Zone midpoint - optimal entry point."""
        return (self.upper + self.lower) / 2

    @property
    def height(self) -> float:
        """Zone height in price terms."""
        return self.upper - self.lower

    @property
    def success_rate(self) -> float:
        """Historical reversal success rate."""
        total = self.successful_reversals + self.failed_breaks
        if total == 0:
            return 0.5  # Default 50% for untested zones
        return self.successful_reversals / total

    @property
    def confidence_score(self) -> float:
        """
        Overall confidence score (0-100) based on:
        - Strength
        - Volume profile
        - Historical success
        - Freshness
        """
        base_score = self.strength.value * 20  # 20-80 based on strength

        # Volume bonus (up to +10)
        volume_bonus = min(10, (self.volume_profile - 1) * 5) if self.volume_profile > 1 else 0

        # Success rate adjustment (-10 to +10)
        success_adj = (self.success_rate - 0.5) * 20

        # Freshness bonus (+10 for fresh zones)
        fresh_bonus = 10 if self.is_fresh else 0

        # Touch penalty (zones touched too many times lose strength)
        touch_penalty = min(20, self.touch_count * 5)

        score = base_score + volume_bonus + success_adj + fresh_bonus - touch_penalty
        return max(0, min(100, score))

    def contains_price(self, price: float) -> bool:
        """Check if price is within zone bounds."""
        return self.lower <= price <= self.upper

    def distance_to_price(self, price: float) -> float:
        """Calculate distance from price to zone midpoint."""
        return abs(price - self.midpoint)

    def to_dict(self) -> dict:
        """Convert zone to dictionary for serialization."""
        return {
            'type': self.zone_type.value,
            'upper': self.upper,
            'lower': self.lower,
            'midpoint': self.midpoint,
            'height': self.height,
            'formation_time': str(self.formation_time),
            'strength': self.strength.name,
            'confidence': self.confidence_score,
            'touch_count': self.touch_count,
            'success_rate': self.success_rate,
            'is_fresh': self.is_fresh,
            'is_valid': self.is_valid,
        }


class ZoneDetector:
    """
    Detects supply and demand zones from price action.

    Detection Methods:
    1. Marubozu Detection: Strong candles with small wicks
    2. Wick Extreme Detection: Long wicks indicating rejection
    3. Volume Spike Detection: Unusual volume at price levels
    4. Pivot Point Detection: Swing highs/lows
    """

    def __init__(
        self,
        min_body_ratio: float = 0.6,  # Minimum body/range for Marubozu
        wick_threshold: float = 0.3,  # Wick must be > 30% of range for rejection
        volume_threshold: float = 1.5,  # Volume must be 1.5x average
        zone_extension: float = 0.002,  # Extend zone by 0.2% for buffer
        lookback_periods: int = 100,  # Bars to analyze for zones
    ):
        self.min_body_ratio = min_body_ratio
        self.wick_threshold = wick_threshold
        self.volume_threshold = volume_threshold
        self.zone_extension = zone_extension
        self.lookback_periods = lookback_periods

    def detect_zones(self, df: pd.DataFrame) -> List[Zone]:
        """
        Main zone detection method. Combines multiple detection strategies.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            List of detected Zone objects
        """
        zones = []

        # Method 1: Marubozu-based zones
        marubozu_zones = self._detect_marubozu_zones(df)
        zones.extend(marubozu_zones)

        # Method 2: Wick rejection zones
        wick_zones = self._detect_wick_zones(df)
        zones.extend(wick_zones)

        # Method 3: Volume spike zones
        volume_zones = self._detect_volume_zones(df)
        zones.extend(volume_zones)

        # Method 4: Pivot-based zones
        pivot_zones = self._detect_pivot_zones(df)
        zones.extend(pivot_zones)

        # Merge overlapping zones
        merged_zones = self._merge_overlapping_zones(zones)

        # Update zone status based on subsequent price action
        updated_zones = self._update_zone_status(merged_zones, df)

        return updated_zones

    def _detect_marubozu_zones(self, df: pd.DataFrame) -> List[Zone]:
        """
        Detect zones from Marubozu candles (strong momentum candles).

        A Marubozu has:
        - Large body relative to range
        - Small or no wicks
        - High volume

        The base of a bullish Marubozu = demand zone
        The top of a bearish Marubozu = supply zone
        """
        zones = []

        # Calculate body and wick ratios
        df = df.copy()
        df['range'] = df['high'] - df['low']
        df['body'] = abs(df['close'] - df['open'])
        df['body_ratio'] = df['body'] / df['range'].replace(0, np.nan)

        # Volume relative to average
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['rel_volume'] = df['volume'] / df['vol_sma'].replace(0, np.nan)

        # Identify Marubozu candles
        is_marubozu = df['body_ratio'] >= self.min_body_ratio
        is_high_volume = df['rel_volume'] >= self.volume_threshold

        # Bullish Marubozu (close > open) -> Demand zone at base
        bullish_marubozu = is_marubozu & is_high_volume & (df['close'] > df['open'])

        for idx in df[bullish_marubozu].index:
            row = df.loc[idx]
            zone_lower = row['low'] * (1 - self.zone_extension)
            zone_upper = row['open'] * (1 + self.zone_extension)

            zones.append(Zone(
                zone_type=ZoneType.DEMAND,
                upper=zone_upper,
                lower=zone_lower,
                formation_time=idx,
                formation_idx=df.index.get_loc(idx),
                strength=self._calculate_strength(row['body_ratio'], row['rel_volume']),
                volume_profile=row['rel_volume'],
                body_ratio=row['body_ratio'],
            ))

        # Bearish Marubozu (close < open) -> Supply zone at top
        bearish_marubozu = is_marubozu & is_high_volume & (df['close'] < df['open'])

        for idx in df[bearish_marubozu].index:
            row = df.loc[idx]
            zone_lower = row['open'] * (1 - self.zone_extension)
            zone_upper = row['high'] * (1 + self.zone_extension)

            zones.append(Zone(
                zone_type=ZoneType.SUPPLY,
                upper=zone_upper,
                lower=zone_lower,
                formation_time=idx,
                formation_idx=df.index.get_loc(idx),
                strength=self._calculate_strength(row['body_ratio'], row['rel_volume']),
                volume_profile=row['rel_volume'],
                body_ratio=row['body_ratio'],
            ))

        return zones

    def _detect_wick_zones(self, df: pd.DataFrame) -> List[Zone]:
        """
        Detect zones from long wick rejections.

        Long lower wick = demand zone (buyers rejected lower prices)
        Long upper wick = supply zone (sellers rejected higher prices)
        """
        zones = []

        df = df.copy()
        df['range'] = df['high'] - df['low']
        df['body'] = abs(df['close'] - df['open'])

        # Calculate wick sizes
        df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
        df['upper_wick_ratio'] = df['upper_wick'] / df['range'].replace(0, np.nan)
        df['lower_wick_ratio'] = df['lower_wick'] / df['range'].replace(0, np.nan)

        # Volume relative to average
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['rel_volume'] = df['volume'] / df['vol_sma'].replace(0, np.nan)

        # Long lower wick -> Demand zone
        long_lower_wick = df['lower_wick_ratio'] >= self.wick_threshold

        for idx in df[long_lower_wick].index:
            row = df.loc[idx]
            # Demand zone is at the wick extreme
            zone_lower = row['low'] * (1 - self.zone_extension)
            zone_upper = min(row['open'], row['close'])

            zones.append(Zone(
                zone_type=ZoneType.DEMAND,
                upper=zone_upper,
                lower=zone_lower,
                formation_time=idx,
                formation_idx=df.index.get_loc(idx),
                strength=ZoneStrength.MODERATE,
                volume_profile=row['rel_volume'] if pd.notna(row['rel_volume']) else 1.0,
                wick_rejection=row['lower_wick_ratio'],
            ))

        # Long upper wick -> Supply zone
        long_upper_wick = df['upper_wick_ratio'] >= self.wick_threshold

        for idx in df[long_upper_wick].index:
            row = df.loc[idx]
            # Supply zone is at the wick extreme
            zone_lower = max(row['open'], row['close'])
            zone_upper = row['high'] * (1 + self.zone_extension)

            zones.append(Zone(
                zone_type=ZoneType.SUPPLY,
                upper=zone_upper,
                lower=zone_lower,
                formation_time=idx,
                formation_idx=df.index.get_loc(idx),
                strength=ZoneStrength.MODERATE,
                volume_profile=row['rel_volume'] if pd.notna(row['rel_volume']) else 1.0,
                wick_rejection=row['upper_wick_ratio'],
            ))

        return zones

    def _detect_volume_zones(self, df: pd.DataFrame) -> List[Zone]:
        """
        Detect zones from volume spikes with price rejection.

        High volume + reversal = institutional activity zone
        """
        zones = []

        df = df.copy()
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_std'] = df['volume'].rolling(20).std()
        df['vol_zscore'] = (df['volume'] - df['vol_sma']) / df['vol_std'].replace(0, np.nan)

        # Significant volume spikes (> 2 standard deviations)
        volume_spike = df['vol_zscore'] > 2

        for idx in df[volume_spike].index:
            row = df.loc[idx]
            pos = df.index.get_loc(idx)

            # Need at least one bar after to determine direction
            if pos >= len(df) - 1:
                continue

            next_row = df.iloc[pos + 1]

            # Check if this was a reversal
            is_bullish_reversal = (row['close'] < row['open']) and (next_row['close'] > next_row['open'])
            is_bearish_reversal = (row['close'] > row['open']) and (next_row['close'] < next_row['open'])

            if is_bullish_reversal:
                zones.append(Zone(
                    zone_type=ZoneType.DEMAND,
                    upper=max(row['open'], row['close']),
                    lower=row['low'] * (1 - self.zone_extension),
                    formation_time=idx,
                    formation_idx=pos,
                    strength=ZoneStrength.STRONG,
                    volume_profile=row['vol_zscore'],
                ))
            elif is_bearish_reversal:
                zones.append(Zone(
                    zone_type=ZoneType.SUPPLY,
                    upper=row['high'] * (1 + self.zone_extension),
                    lower=min(row['open'], row['close']),
                    formation_time=idx,
                    formation_idx=pos,
                    strength=ZoneStrength.STRONG,
                    volume_profile=row['vol_zscore'],
                ))

        return zones

    def _detect_pivot_zones(self, df: pd.DataFrame, window: int = 5) -> List[Zone]:
        """
        Detect zones from swing pivot points.

        Swing high = potential supply zone
        Swing low = potential demand zone
        """
        zones = []

        df = df.copy()

        # Find swing highs (local maxima)
        df['swing_high'] = df['high'].rolling(window=window, center=True).apply(
            lambda x: x.iloc[window // 2] == x.max(), raw=False
        )

        # Find swing lows (local minima)
        df['swing_low'] = df['low'].rolling(window=window, center=True).apply(
            lambda x: x.iloc[window // 2] == x.min(), raw=False
        )

        # Volume context
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['rel_volume'] = df['volume'] / df['vol_sma'].replace(0, np.nan)

        # Create supply zones at swing highs
        for idx in df[df['swing_high'] == 1].index:
            row = df.loc[idx]
            zones.append(Zone(
                zone_type=ZoneType.SUPPLY,
                upper=row['high'] * (1 + self.zone_extension),
                lower=row['high'] * (1 - self.zone_extension),
                formation_time=idx,
                formation_idx=df.index.get_loc(idx),
                strength=ZoneStrength.MODERATE,
                volume_profile=row['rel_volume'] if pd.notna(row['rel_volume']) else 1.0,
            ))

        # Create demand zones at swing lows
        for idx in df[df['swing_low'] == 1].index:
            row = df.loc[idx]
            zones.append(Zone(
                zone_type=ZoneType.DEMAND,
                upper=row['low'] * (1 + self.zone_extension),
                lower=row['low'] * (1 - self.zone_extension),
                formation_time=idx,
                formation_idx=df.index.get_loc(idx),
                strength=ZoneStrength.MODERATE,
                volume_profile=row['rel_volume'] if pd.notna(row['rel_volume']) else 1.0,
            ))

        return zones

    def _calculate_strength(self, body_ratio: float, rel_volume: float) -> ZoneStrength:
        """Calculate zone strength based on formation characteristics."""
        score = 0

        # Body ratio contribution
        if body_ratio >= 0.9:
            score += 3
        elif body_ratio >= 0.75:
            score += 2
        elif body_ratio >= 0.6:
            score += 1

        # Volume contribution
        if rel_volume >= 3.0:
            score += 3
        elif rel_volume >= 2.0:
            score += 2
        elif rel_volume >= 1.5:
            score += 1

        # Map score to strength
        if score >= 5:
            return ZoneStrength.EXTREME
        elif score >= 4:
            return ZoneStrength.STRONG
        elif score >= 2:
            return ZoneStrength.MODERATE
        else:
            return ZoneStrength.WEAK

    def _merge_overlapping_zones(self, zones: List[Zone], overlap_threshold: float = 0.5) -> List[Zone]:
        """
        Merge overlapping zones of the same type.

        Two zones overlap if they share > 50% of their height.
        """
        if not zones:
            return []

        # Separate by type
        demand_zones = [z for z in zones if z.zone_type == ZoneType.DEMAND]
        supply_zones = [z for z in zones if z.zone_type == ZoneType.SUPPLY]

        merged_demand = self._merge_zone_list(demand_zones, overlap_threshold)
        merged_supply = self._merge_zone_list(supply_zones, overlap_threshold)

        return merged_demand + merged_supply

    def _merge_zone_list(self, zones: List[Zone], overlap_threshold: float) -> List[Zone]:
        """Merge a list of same-type zones."""
        if not zones:
            return []

        # Sort by lower bound
        sorted_zones = sorted(zones, key=lambda z: z.lower)
        merged = [sorted_zones[0]]

        for zone in sorted_zones[1:]:
            last = merged[-1]

            # Check overlap
            overlap = min(last.upper, zone.upper) - max(last.lower, zone.lower)
            min_height = min(last.height, zone.height)

            if overlap > min_height * overlap_threshold:
                # Merge zones
                new_lower = min(last.lower, zone.lower)
                new_upper = max(last.upper, zone.upper)

                # Keep stronger zone's properties
                if zone.strength.value > last.strength.value:
                    merged[-1] = Zone(
                        zone_type=zone.zone_type,
                        upper=new_upper,
                        lower=new_lower,
                        formation_time=zone.formation_time,
                        formation_idx=zone.formation_idx,
                        strength=zone.strength,
                        volume_profile=max(last.volume_profile, zone.volume_profile),
                        body_ratio=max(last.body_ratio, zone.body_ratio),
                    )
                else:
                    merged[-1] = Zone(
                        zone_type=last.zone_type,
                        upper=new_upper,
                        lower=new_lower,
                        formation_time=last.formation_time,
                        formation_idx=last.formation_idx,
                        strength=last.strength,
                        volume_profile=max(last.volume_profile, zone.volume_profile),
                        body_ratio=max(last.body_ratio, zone.body_ratio),
                    )
            else:
                merged.append(zone)

        return merged

    def _update_zone_status(self, zones: List[Zone], df: pd.DataFrame) -> List[Zone]:
        """
        Update zone status based on subsequent price action.

        - Count touches
        - Track successful reversals vs failed breaks
        - Mark zones as no longer fresh
        - Invalidate broken zones
        """
        for zone in zones:
            # Get price action after zone formation
            subsequent_data = df.iloc[zone.formation_idx + 1:]

            if subsequent_data.empty:
                continue

            for idx, row in subsequent_data.iterrows():
                # Check if price touched the zone
                touched = zone.contains_price(row['low']) or zone.contains_price(row['high'])

                if touched:
                    zone.is_fresh = False
                    zone.touch_count += 1

                    # Check if it was a successful reversal or failed break
                    pos = df.index.get_loc(idx)
                    if pos < len(df) - 1:
                        next_close = df.iloc[pos + 1]['close']

                        if zone.zone_type == ZoneType.DEMAND:
                            # Demand zone: successful if price bounced up
                            if next_close > zone.midpoint:
                                zone.successful_reversals += 1
                            else:
                                zone.failed_breaks += 1
                        else:
                            # Supply zone: successful if price rejected down
                            if next_close < zone.midpoint:
                                zone.successful_reversals += 1
                            else:
                                zone.failed_breaks += 1

                # Check if zone was decisively broken
                if zone.zone_type == ZoneType.DEMAND:
                    if row['close'] < zone.lower:
                        zone.is_valid = False
                        break
                else:
                    if row['close'] > zone.upper:
                        zone.is_valid = False
                        break

        return zones

    def get_active_zones(
        self,
        zones: List[Zone],
        current_price: float,
        max_distance_pct: float = 0.02,  # 2% from current price
    ) -> Tuple[List[Zone], List[Zone]]:
        """
        Get zones that are currently actionable (close to price).

        Args:
            zones: List of detected zones
            current_price: Current market price
            max_distance_pct: Maximum distance from price as percentage

        Returns:
            Tuple of (nearby_demand_zones, nearby_supply_zones)
        """
        max_distance = current_price * max_distance_pct

        demand_zones = []
        supply_zones = []

        for zone in zones:
            if not zone.is_valid:
                continue

            distance = zone.distance_to_price(current_price)

            if distance <= max_distance:
                if zone.zone_type == ZoneType.DEMAND:
                    demand_zones.append(zone)
                else:
                    supply_zones.append(zone)

        # Sort by confidence score (descending)
        demand_zones.sort(key=lambda z: z.confidence_score, reverse=True)
        supply_zones.sort(key=lambda z: z.confidence_score, reverse=True)

        return demand_zones, supply_zones


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    import sys
    import os; sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data.fetcher import DataFetcher

    # Fetch data
    fetcher = DataFetcher()
    data = fetcher.fetch_market_data('QQQ', '5m', '5d')

    # Detect zones
    detector = ZoneDetector()
    zones = detector.detect_zones(data.ohlcv)

    current_price = data.metadata['current_price']

    print(f"Current QQQ Price: ${current_price:.2f}")
    print(f"\nTotal zones detected: {len(zones)}")
    print(f"Valid zones: {len([z for z in zones if z.is_valid])}")

    # Get nearby zones
    demand_zones, supply_zones = detector.get_active_zones(zones, current_price)

    print(f"\n=== NEARBY DEMAND ZONES ===")
    for z in demand_zones[:5]:
        print(f"  ${z.lower:.2f} - ${z.upper:.2f} (mid: ${z.midpoint:.2f})")
        print(f"    Confidence: {z.confidence_score:.0f}% | Strength: {z.strength.name}")
        print(f"    Fresh: {z.is_fresh} | Touches: {z.touch_count}")

    print(f"\n=== NEARBY SUPPLY ZONES ===")
    for z in supply_zones[:5]:
        print(f"  ${z.lower:.2f} - ${z.upper:.2f} (mid: ${z.midpoint:.2f})")
        print(f"    Confidence: {z.confidence_score:.0f}% | Strength: {z.strength.name}")
        print(f"    Fresh: {z.is_fresh} | Touches: {z.touch_count}")
