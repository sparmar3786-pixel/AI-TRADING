"""
Market Regime Detector
=======================
Simple, robust rules to know WHEN to trade.

No ML here - just battle-tested logic:
- Trending markets: Trade with trend
- Ranging markets: Fade extremes
- Volatile markets: Reduce size or sit out
- Dead markets: Don't force trades

This is MORE important than entry signals.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class MarketRegime(Enum):
    """Market states - simple and clear."""
    STRONG_UPTREND = "strong_uptrend"      # Buy dips aggressively
    UPTREND = "uptrend"                     # Buy dips carefully
    RANGING = "ranging"                     # Mean reversion plays
    DOWNTREND = "downtrend"                 # Short rallies carefully
    STRONG_DOWNTREND = "strong_downtrend"  # Short rallies aggressively
    VOLATILE = "volatile"                   # Reduce size 50%
    CRISIS = "crisis"                       # Cash only


class TradingMode(Enum):
    """What we should do in each regime."""
    AGGRESSIVE_LONG = "aggressive_long"    # Full size longs
    CAUTIOUS_LONG = "cautious_long"        # Half size longs
    RANGE_TRADE = "range_trade"            # Both directions, tight stops
    CAUTIOUS_SHORT = "cautious_short"      # Half size shorts
    AGGRESSIVE_SHORT = "aggressive_short"  # Full size shorts
    REDUCED_SIZE = "reduced_size"          # Quarter size only
    CASH = "cash"                          # No trades


@dataclass
class RegimeAnalysis:
    """Current market regime analysis."""
    regime: MarketRegime
    trading_mode: TradingMode
    confidence: float  # 0-100

    # Key metrics
    trend_strength: float      # -100 to +100
    volatility_percentile: float  # 0-100
    vix_level: float

    # Position sizing multiplier
    size_multiplier: float     # 0.0 to 1.0

    # Allowed directions
    allow_longs: bool
    allow_shorts: bool

    # Context
    reasoning: str

    def to_dict(self) -> dict:
        return {
            'regime': self.regime.value,
            'mode': self.trading_mode.value,
            'size_mult': self.size_multiplier,
            'allow_longs': self.allow_longs,
            'allow_shorts': self.allow_shorts,
            'reasoning': self.reasoning,
        }


class RegimeDetector:
    """
    Detects market regime using simple, robust rules.

    Rules (no optimization needed):
    1. Price vs 20/50 SMA for trend
    2. ADX for trend strength
    3. ATR percentile for volatility
    4. VIX level for fear
    """

    def __init__(self):
        # Fixed thresholds - NOT optimized
        self.vix_crisis = 35      # Above = crisis mode
        self.vix_high = 25        # Above = elevated caution
        self.vix_low = 15         # Below = complacent, watch for reversal

        self.adx_strong = 25      # Above = trending
        self.adx_weak = 15        # Below = ranging

        self.vol_high_pct = 80    # Top 20% volatility = reduce size

    def analyze(
        self,
        df: pd.DataFrame,
        vix_level: float = None,
    ) -> RegimeAnalysis:
        """
        Analyze current market regime.

        Args:
            df: OHLCV DataFrame (needs 50+ bars)
            vix_level: Current VIX (optional)

        Returns:
            RegimeAnalysis with trading guidance
        """
        if len(df) < 50:
            return self._default_regime()

        # Calculate indicators
        close = df['close']
        high = df['high']
        low = df['low']

        # Moving averages
        sma_20 = close.rolling(20).mean()
        sma_50 = close.rolling(50).mean()

        current_price = close.iloc[-1]
        current_sma20 = sma_20.iloc[-1]
        current_sma50 = sma_50.iloc[-1]

        # Trend direction
        above_20 = current_price > current_sma20
        above_50 = current_price > current_sma50
        sma20_above_50 = current_sma20 > current_sma50

        # ADX for trend strength
        adx = self._calculate_adx(df)
        current_adx = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 20

        # ATR for volatility
        atr = self._calculate_atr(df)
        atr_percentile = (atr.rank(pct=True) * 100).iloc[-1]

        # Trend strength score (-100 to +100)
        trend_strength = self._calculate_trend_strength(
            above_20, above_50, sma20_above_50, current_adx
        )

        # VIX analysis
        vix = vix_level or 20  # Default if not provided

        # Determine regime
        regime, mode, reasoning = self._classify_regime(
            trend_strength, current_adx, atr_percentile, vix
        )

        # Position sizing
        size_mult = self._get_size_multiplier(regime, atr_percentile, vix)

        # Allowed directions
        allow_longs, allow_shorts = self._get_allowed_directions(regime)

        return RegimeAnalysis(
            regime=regime,
            trading_mode=mode,
            confidence=min(100, current_adx * 2),
            trend_strength=trend_strength,
            volatility_percentile=atr_percentile,
            vix_level=vix,
            size_multiplier=size_mult,
            allow_longs=allow_longs,
            allow_shorts=allow_shorts,
            reasoning=reasoning,
        )

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ADX (Average Directional Index)."""
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

        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()

        return adx

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR."""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(period).mean()

    def _calculate_trend_strength(
        self,
        above_20: bool,
        above_50: bool,
        sma20_above_50: bool,
        adx: float,
    ) -> float:
        """Calculate trend strength from -100 to +100."""
        score = 0

        # Price position
        if above_20:
            score += 25
        else:
            score -= 25

        if above_50:
            score += 25
        else:
            score -= 25

        # SMA alignment
        if sma20_above_50:
            score += 25
        else:
            score -= 25

        # ADX contribution (scales the score)
        adx_factor = min(adx / 25, 1.0)  # Caps at ADX 25
        score = score * (0.5 + 0.5 * adx_factor)

        return max(-100, min(100, score))

    def _classify_regime(
        self,
        trend_strength: float,
        adx: float,
        vol_pct: float,
        vix: float,
    ) -> Tuple[MarketRegime, TradingMode, str]:
        """Classify market regime."""

        # Crisis check first
        if vix >= self.vix_crisis:
            return (
                MarketRegime.CRISIS,
                TradingMode.CASH,
                f"VIX at {vix:.1f} - crisis mode, preserve capital"
            )

        # High volatility
        if vol_pct >= self.vol_high_pct or vix >= self.vix_high:
            return (
                MarketRegime.VOLATILE,
                TradingMode.REDUCED_SIZE,
                f"Elevated volatility (ATR {vol_pct:.0f}%, VIX {vix:.1f}) - reduce size"
            )

        # Trending markets
        if adx >= self.adx_strong:
            if trend_strength >= 50:
                return (
                    MarketRegime.STRONG_UPTREND,
                    TradingMode.AGGRESSIVE_LONG,
                    f"Strong uptrend (ADX {adx:.0f}, strength +{trend_strength:.0f})"
                )
            elif trend_strength >= 20:
                return (
                    MarketRegime.UPTREND,
                    TradingMode.CAUTIOUS_LONG,
                    f"Uptrend (ADX {adx:.0f}, strength +{trend_strength:.0f})"
                )
            elif trend_strength <= -50:
                return (
                    MarketRegime.STRONG_DOWNTREND,
                    TradingMode.AGGRESSIVE_SHORT,
                    f"Strong downtrend (ADX {adx:.0f}, strength {trend_strength:.0f})"
                )
            elif trend_strength <= -20:
                return (
                    MarketRegime.DOWNTREND,
                    TradingMode.CAUTIOUS_SHORT,
                    f"Downtrend (ADX {adx:.0f}, strength {trend_strength:.0f})"
                )

        # Ranging market
        return (
            MarketRegime.RANGING,
            TradingMode.RANGE_TRADE,
            f"Ranging market (ADX {adx:.0f}) - fade extremes"
        )

    def _get_size_multiplier(
        self,
        regime: MarketRegime,
        vol_pct: float,
        vix: float,
    ) -> float:
        """Get position size multiplier based on conditions."""
        base = {
            MarketRegime.STRONG_UPTREND: 1.0,
            MarketRegime.UPTREND: 0.75,
            MarketRegime.RANGING: 0.5,
            MarketRegime.DOWNTREND: 0.75,
            MarketRegime.STRONG_DOWNTREND: 1.0,
            MarketRegime.VOLATILE: 0.25,
            MarketRegime.CRISIS: 0.0,
        }.get(regime, 0.5)

        # Additional reduction for high VIX
        if vix > self.vix_high:
            base *= 0.5

        return base

    def _get_allowed_directions(
        self,
        regime: MarketRegime,
    ) -> Tuple[bool, bool]:
        """Get allowed trade directions."""
        directions = {
            MarketRegime.STRONG_UPTREND: (True, False),   # Longs only
            MarketRegime.UPTREND: (True, False),          # Longs only
            MarketRegime.RANGING: (True, True),           # Both
            MarketRegime.DOWNTREND: (False, True),        # Shorts only
            MarketRegime.STRONG_DOWNTREND: (False, True), # Shorts only
            MarketRegime.VOLATILE: (True, True),          # Both but reduced
            MarketRegime.CRISIS: (False, False),          # None
        }
        return directions.get(regime, (False, False))

    def _default_regime(self) -> RegimeAnalysis:
        """Return safe default when data insufficient."""
        return RegimeAnalysis(
            regime=MarketRegime.RANGING,
            trading_mode=TradingMode.REDUCED_SIZE,
            confidence=0,
            trend_strength=0,
            volatility_percentile=50,
            vix_level=20,
            size_multiplier=0.25,
            allow_longs=True,
            allow_shorts=True,
            reasoning="Insufficient data - using conservative defaults",
        )


# Quick test
if __name__ == "__main__":
    import yfinance as yf

    print("=" * 50)
    print("  MARKET REGIME DETECTOR")
    print("=" * 50)

    detector = RegimeDetector()

    for symbol in ['SPY', 'QQQ']:
        print(f"\n{symbol}:")
        df = yf.download(symbol, period='6mo', interval='1d', progress=False)

        # Get VIX
        vix_df = yf.download('^VIX', period='5d', interval='1d', progress=False)
        vix = vix_df['Close'].iloc[-1] if not vix_df.empty else 20

        analysis = detector.analyze(df, vix)

        print(f"  Regime: {analysis.regime.value}")
        print(f"  Mode: {analysis.trading_mode.value}")
        print(f"  Trend Strength: {analysis.trend_strength:+.0f}")
        print(f"  VIX: {analysis.vix_level:.1f}")
        print(f"  Size Multiplier: {analysis.size_multiplier:.0%}")
        print(f"  Allow Longs: {analysis.allow_longs}")
        print(f"  Allow Shorts: {analysis.allow_shorts}")
        print(f"  Reasoning: {analysis.reasoning}")
