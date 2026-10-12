"""
The Simple Edge - One File, One Strategy
==========================================
This is it. One simple strategy that works.

STOP adding complexity. This is enough.

THE EDGE:
1. Wait for DAILY trend direction
2. Wait for price to pull back to zone
3. Wait for candle confirmation
4. Enter with proper size
5. Exit at targets or stop

That's it. Do this 100 times with discipline = financial freedom.
"""

import os
import sys
from datetime import datetime, time
from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.regime import RegimeDetector, MarketRegime, TradingMode
from core.risk_manager import RiskManager, RiskDecision
from core.journal import TradingJournal, JournalEntry, TradeQuality, EmotionalState


class SetupQuality(Enum):
    """How good is this setup?"""
    PERFECT = "perfect"    # Take full size
    GOOD = "good"          # Take 75% size
    OKAY = "okay"          # Take 50% size
    SKIP = "skip"          # Don't trade


@dataclass
class SimpleSetup:
    """A trading setup - simple and clear."""
    symbol: str
    direction: str       # "LONG" or "SHORT"
    quality: SetupQuality

    # Levels
    entry: float
    stop: float
    target_1: float      # 1R - take 1/3
    target_2: float      # 2R - take 1/3
    target_3: float      # 3R - let it run

    # Risk
    risk_per_share: float
    shares: int
    dollar_risk: float

    # Why
    reasons: List[str]

    # When
    timestamp: datetime

    def __str__(self) -> str:
        return f"""
{'='*50}
{self.quality.value.upper()} {self.direction} on {self.symbol}
{'='*50}
Entry:  ${self.entry:.2f}
Stop:   ${self.stop:.2f}  (Risk: ${self.risk_per_share:.2f})
T1:     ${self.target_1:.2f}  (1R - sell 1/3)
T2:     ${self.target_2:.2f}  (2R - sell 1/3)
T3:     ${self.target_3:.2f}  (3R - trail stop)

Shares: {self.shares}
Risk:   ${self.dollar_risk:.2f}

Reasons:
{chr(10).join(f'  • {r}' for r in self.reasons)}
{'='*50}
"""


class SimpleEdge:
    """
    The simple edge that actually works.

    Rules:
    1. Only trade with the daily trend
    2. Only enter at zones with confirmation
    3. Never risk more than 2%
    4. Always use stops
    5. Take profits at 1R, 2R, trail 3R
    """

    def __init__(
        self,
        account_balance: float = 10000,
        tiingo_api_key: str = None,
    ):
        self.account_balance = account_balance
        self.api_key = tiingo_api_key or os.environ.get("TIINGO_API_KEY")

        # Core components
        self.regime_detector = RegimeDetector()
        self.risk_manager = RiskManager(account_balance)
        self.journal = TradingJournal()

        # Import data fetchers
        try:
            from data.tiingo_fetcher import TiingoFetcher
            self.tiingo = TiingoFetcher(self.api_key) if self.api_key else None
        except:
            self.tiingo = None

        try:
            from data.fetcher import DataFetcher
            self.fetcher = DataFetcher()
        except:
            self.fetcher = None

    def scan(self, symbols: List[str]) -> List[SimpleSetup]:
        """
        Scan for setups. Simple logic.
        """
        setups = []

        print("\n" + "=" * 60)
        print("  SIMPLE EDGE SCANNER")
        print("=" * 60)
        print(f"  Account: ${self.account_balance:,.0f}")
        print(f"  Symbols: {', '.join(symbols)}")
        print("=" * 60)

        for symbol in symbols:
            setup = self._analyze(symbol)
            if setup and setup.quality != SetupQuality.SKIP:
                setups.append(setup)
                print(setup)

        if not setups:
            print("\n  No setups found. This is FINE.")
            print("  Good traders wait. Bad traders force.")

        return setups

    def _analyze(self, symbol: str) -> Optional[SimpleSetup]:
        """Analyze one symbol."""
        print(f"\n{symbol}:")

        # Step 1: Get daily data and regime
        daily_df = self._get_daily_data(symbol)
        if daily_df is None or len(daily_df) < 50:
            print("  ✗ Not enough data")
            return None

        regime = self.regime_detector.analyze(daily_df)
        print(f"  Regime: {regime.regime.value}")
        print(f"  Mode: {regime.trading_mode.value}")

        # Step 2: Check if we should trade this regime
        if regime.trading_mode == TradingMode.CASH:
            print("  ✗ Cash mode - no trades")
            return None

        # Step 3: Determine allowed direction
        if regime.allow_longs and not regime.allow_shorts:
            direction = "LONG"
        elif regime.allow_shorts and not regime.allow_longs:
            direction = "SHORT"
        elif regime.allow_longs and regime.allow_shorts:
            # In ranging market, check which side is better
            direction = self._determine_direction(daily_df)
        else:
            print("  ✗ No direction allowed")
            return None

        print(f"  Direction: {direction}")

        # Step 4: Find zone
        zone = self._find_zone(daily_df, direction)
        if zone is None:
            print("  ✗ No valid zone nearby")
            return None

        print(f"  Zone: ${zone['lower']:.2f} - ${zone['upper']:.2f}")

        # Step 5: Check for confirmation candle
        confirmation = self._check_confirmation(daily_df, direction)
        if not confirmation:
            print("  ✗ No confirmation candle")
            return None

        print(f"  ✓ Confirmation: {confirmation}")

        # Step 6: Calculate levels
        current_price = daily_df['close'].iloc[-1]
        atr = self._calculate_atr(daily_df)

        if direction == "LONG":
            entry = current_price
            stop = zone['lower'] - atr * 0.2
            risk = entry - stop
            target_1 = entry + risk
            target_2 = entry + risk * 2
            target_3 = entry + risk * 3
        else:
            entry = current_price
            stop = zone['upper'] + atr * 0.2
            risk = stop - entry
            target_1 = entry - risk
            target_2 = entry - risk * 2
            target_3 = entry - risk * 3

        # Step 7: Check risk manager
        risk_decision = self.risk_manager.can_take_trade(
            risk_per_share=risk,
            entry_price=entry,
        )

        if not risk_decision.can_trade:
            print(f"  ✗ Risk manager: {risk_decision.reasoning}")
            return None

        # Step 8: Calculate position size
        position = self.risk_manager.calculate_position_size(entry, stop)

        if not position['can_trade']:
            print(f"  ✗ Position: {position['reason']}")
            return None

        # Step 9: Determine quality
        quality = self._assess_quality(regime, zone, confirmation)

        # Build setup
        reasons = [
            f"Regime: {regime.regime.value}",
            f"Zone: {zone['type']} at ${zone['midpoint']:.2f}",
            f"Confirmation: {confirmation}",
        ]

        if risk_decision.warnings:
            reasons.extend([f"⚠️ {w}" for w in risk_decision.warnings])

        return SimpleSetup(
            symbol=symbol,
            direction=direction,
            quality=quality,
            entry=round(entry, 2),
            stop=round(stop, 2),
            target_1=round(target_1, 2),
            target_2=round(target_2, 2),
            target_3=round(target_3, 2),
            risk_per_share=round(risk, 2),
            shares=position['shares'],
            dollar_risk=position['dollar_risk'],
            reasons=reasons,
            timestamp=datetime.now(),
        )

    def _get_daily_data(self, symbol: str):
        """Get daily OHLCV data."""
        if self.tiingo:
            from datetime import timedelta
            end = datetime.now()
            start = end - timedelta(days=100)
            return self.tiingo.get_eod_prices(
                symbol,
                start.strftime('%Y-%m-%d'),
                end.strftime('%Y-%m-%d'),
            )
        elif self.fetcher:
            data = self.fetcher.fetch_market_data(symbol, '1d', '3mo')
            return data.ohlcv if data else None
        return None

    def _determine_direction(self, df) -> str:
        """Determine better direction in ranging market."""
        close = df['close'].iloc[-1]
        sma = df['close'].rolling(20).mean().iloc[-1]
        return "LONG" if close < sma else "SHORT"

    def _find_zone(self, df, direction: str) -> Optional[Dict]:
        """Find nearest valid zone."""
        current = df['close'].iloc[-1]

        # Simple zone detection - look for recent swing points
        highs = df['high'].rolling(5, center=True).max()
        lows = df['low'].rolling(5, center=True).min()

        zones = []

        # Find swing lows (demand zones)
        for i in range(10, len(df) - 5):
            if df['low'].iloc[i] == lows.iloc[i]:
                zone = {
                    'type': 'demand',
                    'lower': df['low'].iloc[i],
                    'upper': df['high'].iloc[i],
                    'midpoint': (df['low'].iloc[i] + df['high'].iloc[i]) / 2,
                    'age': len(df) - i,
                }
                zones.append(zone)

        # Find swing highs (supply zones)
        for i in range(10, len(df) - 5):
            if df['high'].iloc[i] == highs.iloc[i]:
                zone = {
                    'type': 'supply',
                    'lower': df['low'].iloc[i],
                    'upper': df['high'].iloc[i],
                    'midpoint': (df['low'].iloc[i] + df['high'].iloc[i]) / 2,
                    'age': len(df) - i,
                }
                zones.append(zone)

        # Filter for direction and proximity
        valid_zones = []
        for zone in zones:
            distance = abs(current - zone['midpoint']) / current

            if distance > 0.05:  # More than 5% away
                continue

            if direction == "LONG" and zone['type'] != 'demand':
                continue
            if direction == "SHORT" and zone['type'] != 'supply':
                continue

            zone['distance'] = distance
            valid_zones.append(zone)

        if not valid_zones:
            return None

        # Return closest zone
        return min(valid_zones, key=lambda z: z['distance'])

    def _check_confirmation(self, df, direction: str) -> Optional[str]:
        """Check for confirmation candle."""
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        body = abs(curr['close'] - curr['open'])
        range_ = curr['high'] - curr['low']

        if range_ == 0:
            return None

        body_ratio = body / range_

        # Bullish confirmation
        if direction == "LONG":
            # Bullish engulfing
            if (prev['close'] < prev['open'] and
                curr['close'] > curr['open'] and
                curr['close'] > prev['open']):
                return "bullish_engulfing"

            # Hammer
            lower_wick = curr[['open', 'close']].min() - curr['low']
            if body_ratio < 0.3 and lower_wick > body * 2:
                return "hammer"

        # Bearish confirmation
        else:
            # Bearish engulfing
            if (prev['close'] > prev['open'] and
                curr['close'] < curr['open'] and
                curr['close'] < prev['open']):
                return "bearish_engulfing"

            # Shooting star
            upper_wick = curr['high'] - curr[['open', 'close']].max()
            if body_ratio < 0.3 and upper_wick > body * 2:
                return "shooting_star"

        return None

    def _calculate_atr(self, df, period: int = 14):
        """Calculate ATR."""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def _assess_quality(self, regime, zone, confirmation) -> SetupQuality:
        """Assess setup quality."""
        score = 0

        # Regime strength
        if regime.regime in [MarketRegime.STRONG_UPTREND, MarketRegime.STRONG_DOWNTREND]:
            score += 3
        elif regime.regime in [MarketRegime.UPTREND, MarketRegime.DOWNTREND]:
            score += 2
        else:
            score += 1

        # Zone freshness
        if zone['age'] < 10:
            score += 2
        elif zone['age'] < 20:
            score += 1

        # Confirmation strength
        if 'engulfing' in confirmation:
            score += 2
        else:
            score += 1

        # Classify
        if score >= 6:
            return SetupQuality.PERFECT
        elif score >= 4:
            return SetupQuality.GOOD
        elif score >= 2:
            return SetupQuality.OKAY
        else:
            return SetupQuality.SKIP

    def daily_routine(self):
        """
        Your daily trading routine.
        """
        print("""
╔══════════════════════════════════════════════════════════════╗
║                    DAILY TRADING ROUTINE                      ║
╚══════════════════════════════════════════════════════════════╝

BEFORE MARKET (8:30 AM):
  □ Check overnight news
  □ Review daily charts
  □ Identify key levels
  □ Set alerts at zones

MARKET OPEN (9:30-10:00 AM):
  □ WAIT - Don't trade first 30 minutes
  □ Watch for direction

TRADING SESSION (10:00 AM - 3:45 PM):
  □ Only take A+ setups
  □ Follow position sizing
  □ Use stops ALWAYS
  □ Take profits at targets

MARKET CLOSE (3:45-4:00 PM):
  □ Close any day trades
  □ Review trades
  □ Journal entries

AFTER MARKET:
  □ Update journal
  □ Plan tomorrow
  □ Walk away

WEEKLY:
  □ Review journal
  □ Identify patterns
  □ Adjust if needed

══════════════════════════════════════════════════════════════
""")


# Need pandas for some calculations
try:
    import pandas as pd
except ImportError:
    print("Install pandas: pip install pandas")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║                     THE SIMPLE EDGE                           ║
╚══════════════════════════════════════════════════════════════╝

This is your edge:
  1. Trade with the trend
  2. Enter at zones
  3. Wait for confirmation
  4. Size properly
  5. Use stops
  6. Take profits

That's it. No magic. Just discipline.

Starting scan...
""")

    edge = SimpleEdge(account_balance=10000)

    # Show daily routine
    edge.daily_routine()

    # Scan for setups
    symbols = ['SPY', 'QQQ', 'AAPL', 'NVDA', 'TSLA', 'AMD']
    setups = edge.scan(symbols)

    print(f"\nFound {len(setups)} setups")

    # Show risk status
    decision = edge.risk_manager.can_take_trade(1.0, 100.0)
    print(f"\nRisk Status: {decision.status.value}")
    print(f"Max Risk: ${decision.max_risk_dollars:.0f}")

    # Show daily summary
    summary = edge.risk_manager.get_daily_summary()
    print(f"\nToday's Stats:")
    print(f"  Trades: {summary['trades']}")
    print(f"  P&L: ${summary['gross_pnl']:.2f}")
