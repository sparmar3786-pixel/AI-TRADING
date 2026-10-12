"""
Trade Journal - Learn From Every Trade
========================================
The difference between a gambler and a professional:
Professionals learn from EVERY trade, win or lose.

This journal tracks:
- What you did
- Why you did it
- What happened
- What you learned

Review weekly. Patterns will emerge.
"""

import os
import json
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from enum import Enum
import statistics


class TradeQuality(Enum):
    """Self-assessment of trade quality."""
    A_PLUS = "A+"    # Perfect execution
    A = "A"          # Good trade, followed rules
    B = "B"          # Minor mistakes
    C = "C"          # Broke rules but lucky
    D = "D"          # Broke rules, got punished
    F = "F"          # Complete failure


class EmotionalState(Enum):
    """Emotional state during trade."""
    CALM = "calm"           # Ideal state
    CONFIDENT = "confident" # Good but watch ego
    ANXIOUS = "anxious"     # Size too big?
    FOMO = "fomo"           # Chasing
    REVENGE = "revenge"     # After loss
    EUPHORIC = "euphoric"   # After big win
    BORED = "bored"         # Forcing trades


@dataclass
class JournalEntry:
    """Complete record of a trade."""
    # Trade details
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    target: float
    shares: int

    # Results
    pnl: float
    r_multiple: float
    held_time_minutes: int

    # Context
    market_regime: str
    daily_bias: str
    setup_type: str  # "zone_reversal", "breakout", etc.

    # Self-assessment
    quality: TradeQuality
    emotional_state: EmotionalState
    followed_rules: bool

    # Notes
    entry_reason: str
    exit_reason: str
    what_went_well: str
    what_went_wrong: str
    lesson_learned: str

    # Meta
    timestamp: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        d['quality'] = self.quality.value
        d['emotional_state'] = self.emotional_state.value
        return d


class TradingJournal:
    """
    Personal trading journal.

    Use this to track every trade and learn patterns.
    """

    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'journal'
        )
        os.makedirs(self.data_dir, exist_ok=True)
        self.entries: List[JournalEntry] = []
        self._load_entries()

    def _load_entries(self):
        """Load all journal entries."""
        entries_file = os.path.join(self.data_dir, 'entries.json')
        if os.path.exists(entries_file):
            with open(entries_file, 'r') as f:
                data = json.load(f)
                for e in data:
                    e['timestamp'] = datetime.fromisoformat(e['timestamp'])
                    e['quality'] = TradeQuality(e['quality'])
                    e['emotional_state'] = EmotionalState(e['emotional_state'])
                    self.entries.append(JournalEntry(**e))

    def _save_entries(self):
        """Save all entries."""
        entries_file = os.path.join(self.data_dir, 'entries.json')
        with open(entries_file, 'w') as f:
            json.dump([e.to_dict() for e in self.entries], f, indent=2)

    def add_entry(self, entry: JournalEntry):
        """Add a new journal entry."""
        self.entries.append(entry)
        self._save_entries()

        # Also save daily summary
        self._update_daily_summary(entry)

    def _update_daily_summary(self, entry: JournalEntry):
        """Update daily summary file."""
        today = date.today()
        summary_file = os.path.join(self.data_dir, f'daily_{today}.json')

        summary = {
            'date': str(today),
            'entries': [],
            'total_pnl': 0,
            'total_r': 0,
            'wins': 0,
            'losses': 0,
        }

        if os.path.exists(summary_file):
            with open(summary_file, 'r') as f:
                summary = json.load(f)

        summary['entries'].append(entry.trade_id)
        summary['total_pnl'] += entry.pnl
        summary['total_r'] += entry.r_multiple
        if entry.pnl > 0:
            summary['wins'] += 1
        else:
            summary['losses'] += 1

        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

    def get_stats(self, days: int = 30) -> Dict:
        """Get trading statistics for last N days."""
        cutoff = datetime.now() - timedelta(days=days)
        recent = [e for e in self.entries if e.timestamp >= cutoff]

        if not recent:
            return {'message': 'No trades in this period'}

        wins = [e for e in recent if e.pnl > 0]
        losses = [e for e in recent if e.pnl <= 0]

        total_pnl = sum(e.pnl for e in recent)
        total_r = sum(e.r_multiple for e in recent)

        # Quality breakdown
        quality_counts = {}
        for e in recent:
            q = e.quality.value
            quality_counts[q] = quality_counts.get(q, 0) + 1

        # Emotional state breakdown
        emotion_counts = {}
        for e in recent:
            em = e.emotional_state.value
            emotion_counts[em] = emotion_counts.get(em, 0) + 1

        # Rule following
        followed_rules = sum(1 for e in recent if e.followed_rules)

        # Best and worst
        best = max(recent, key=lambda e: e.r_multiple)
        worst = min(recent, key=lambda e: e.r_multiple)

        return {
            'period_days': days,
            'total_trades': len(recent),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(recent) if recent else 0,
            'total_pnl': total_pnl,
            'total_r': total_r,
            'avg_r_per_trade': total_r / len(recent) if recent else 0,
            'quality_breakdown': quality_counts,
            'emotion_breakdown': emotion_counts,
            'rules_followed_pct': followed_rules / len(recent) if recent else 0,
            'best_trade': {
                'symbol': best.symbol,
                'r_multiple': best.r_multiple,
                'lesson': best.lesson_learned,
            },
            'worst_trade': {
                'symbol': worst.symbol,
                'r_multiple': worst.r_multiple,
                'lesson': worst.lesson_learned,
            },
        }

    def get_patterns(self) -> Dict:
        """Identify patterns in your trading."""
        if len(self.entries) < 10:
            return {'message': 'Need at least 10 trades to identify patterns'}

        patterns = {
            'best_setups': {},
            'worst_setups': {},
            'time_analysis': {},
            'emotional_impact': {},
            'rule_impact': {},
        }

        # Setup analysis
        setup_stats = {}
        for e in self.entries:
            setup = e.setup_type
            if setup not in setup_stats:
                setup_stats[setup] = {'trades': 0, 'wins': 0, 'total_r': 0}
            setup_stats[setup]['trades'] += 1
            if e.pnl > 0:
                setup_stats[setup]['wins'] += 1
            setup_stats[setup]['total_r'] += e.r_multiple

        for setup, stats in setup_stats.items():
            win_rate = stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0
            avg_r = stats['total_r'] / stats['trades'] if stats['trades'] > 0 else 0
            if win_rate >= 0.6 and stats['trades'] >= 5:
                patterns['best_setups'][setup] = {
                    'win_rate': win_rate,
                    'avg_r': avg_r,
                    'trades': stats['trades'],
                }
            elif win_rate <= 0.4 and stats['trades'] >= 5:
                patterns['worst_setups'][setup] = {
                    'win_rate': win_rate,
                    'avg_r': avg_r,
                    'trades': stats['trades'],
                }

        # Emotional impact
        for emotion in EmotionalState:
            emotion_trades = [e for e in self.entries if e.emotional_state == emotion]
            if len(emotion_trades) >= 3:
                avg_r = sum(e.r_multiple for e in emotion_trades) / len(emotion_trades)
                win_rate = sum(1 for e in emotion_trades if e.pnl > 0) / len(emotion_trades)
                patterns['emotional_impact'][emotion.value] = {
                    'avg_r': avg_r,
                    'win_rate': win_rate,
                    'trades': len(emotion_trades),
                }

        # Rule following impact
        followed = [e for e in self.entries if e.followed_rules]
        broke = [e for e in self.entries if not e.followed_rules]

        if followed:
            patterns['rule_impact']['followed_rules'] = {
                'avg_r': sum(e.r_multiple for e in followed) / len(followed),
                'win_rate': sum(1 for e in followed if e.pnl > 0) / len(followed),
                'trades': len(followed),
            }
        if broke:
            patterns['rule_impact']['broke_rules'] = {
                'avg_r': sum(e.r_multiple for e in broke) / len(broke),
                'win_rate': sum(1 for e in broke if e.pnl > 0) / len(broke),
                'trades': len(broke),
            }

        return patterns

    def weekly_review(self) -> str:
        """Generate weekly review summary."""
        stats = self.get_stats(days=7)
        patterns = self.get_patterns()

        review = f"""
╔══════════════════════════════════════════════════════════════╗
║                    WEEKLY TRADING REVIEW                      ║
╚══════════════════════════════════════════════════════════════╝

📊 PERFORMANCE
   Trades: {stats.get('total_trades', 0)}
   Win Rate: {stats.get('win_rate', 0):.1%}
   Total R: {stats.get('total_r', 0):+.1f}R
   Total P&L: ${stats.get('total_pnl', 0):,.2f}

📈 BEST TRADE
   {stats.get('best_trade', {}).get('symbol', 'N/A')}: {stats.get('best_trade', {}).get('r_multiple', 0):+.1f}R
   Lesson: {stats.get('best_trade', {}).get('lesson', 'N/A')}

📉 WORST TRADE
   {stats.get('worst_trade', {}).get('symbol', 'N/A')}: {stats.get('worst_trade', {}).get('r_multiple', 0):+.1f}R
   Lesson: {stats.get('worst_trade', {}).get('lesson', 'N/A')}

🎯 DISCIPLINE
   Rules Followed: {stats.get('rules_followed_pct', 0):.1%}
   Quality Breakdown: {stats.get('quality_breakdown', {})}

💭 EMOTIONAL STATE
   {stats.get('emotion_breakdown', {})}

🔍 KEY PATTERNS
"""
        # Add pattern insights
        if patterns.get('best_setups'):
            review += "   Best Setups:\n"
            for setup, data in patterns['best_setups'].items():
                review += f"      • {setup}: {data['win_rate']:.0%} win rate, {data['avg_r']:.1f}R avg\n"

        if patterns.get('worst_setups'):
            review += "   Avoid These:\n"
            for setup, data in patterns['worst_setups'].items():
                review += f"      • {setup}: {data['win_rate']:.0%} win rate, {data['avg_r']:.1f}R avg\n"

        review += """
══════════════════════════════════════════════════════════════
FOCUS FOR NEXT WEEK:
1.
2.
3.
══════════════════════════════════════════════════════════════
"""
        return review


# Quick entry helper
def quick_journal_entry(
    symbol: str,
    direction: str,
    entry: float,
    exit: float,
    stop: float,
    shares: int,
    setup: str = "zone_reversal",
    notes: str = "",
) -> JournalEntry:
    """Helper to quickly create a journal entry."""
    pnl = (exit - entry) * shares if direction == "LONG" else (entry - exit) * shares
    risk = abs(entry - stop)
    r_mult = (exit - entry) / risk if direction == "LONG" else (entry - exit) / risk

    return JournalEntry(
        trade_id=f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        symbol=symbol,
        direction=direction,
        entry_price=entry,
        exit_price=exit,
        stop_loss=stop,
        target=entry + risk * 2 if direction == "LONG" else entry - risk * 2,
        shares=shares,
        pnl=pnl,
        r_multiple=r_mult,
        held_time_minutes=30,
        market_regime="unknown",
        daily_bias="unknown",
        setup_type=setup,
        quality=TradeQuality.A if r_mult > 0 else TradeQuality.B,
        emotional_state=EmotionalState.CALM,
        followed_rules=True,
        entry_reason=notes or "Setup met criteria",
        exit_reason="Target hit" if r_mult > 0 else "Stop hit",
        what_went_well="",
        what_went_wrong="",
        lesson_learned="",
    )


if __name__ == "__main__":
    print("=" * 50)
    print("  TRADING JOURNAL")
    print("=" * 50)

    journal = TradingJournal()

    # Show stats
    stats = journal.get_stats()
    print(f"\nStats: {json.dumps(stats, indent=2, default=str)}")

    # Show weekly review
    print(journal.weekly_review())
