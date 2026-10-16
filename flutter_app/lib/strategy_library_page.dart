import 'package:flutter/material.dart';

/// Strategy inventory only. Flutter does not execute quant/*.py engines.
/// Live signals still come from the Railway backend + 5-layer gates.
class StrategyLibraryPage extends StatelessWidget {
  const StrategyLibraryPage({super.key});

  static const _items = <_StrategyItem>[
    _StrategyItem(
      name: 'OI Price Action',
      source: 'quant/oi_price_action_engine.py',
      state: StrategyState.bundled,
      statusLine: 'Source on device • live path via backend signals API',
      detail:
          'OI/PCR + price structure + candle/ATR confluence. Missing or stale OI must stay WAIT.',
    ),
    _StrategyItem(
      name: 'Hero Zero',
      source: 'quant/hero_zero.py',
      state: StrategyState.bundled,
      statusLine: 'Expiry-day research engine • candidate only, never auto-order',
      detail:
          'High-risk expiry setup with time-window and premium guards. Not an order approval.',
    ),
    _StrategyItem(
      name: 'Failed-Move / PDH-PDL',
      source: 'quant/failed_move_fade.py',
      state: StrategyState.bundled,
      statusLine: 'Source on device • needs backend routing for live use',
      detail:
          'Acceptance beyond previous-day high/low. Stale candles → WAIT.',
    ),
    _StrategyItem(
      name: 'EMA Crossover',
      source: 'quant/ema_quant_engine.py',
      state: StrategyState.bundled,
      statusLine: 'Source on device • merge + backend test before live',
      detail: 'EMA trend candidate with RSI/ATR filters.',
    ),
    _StrategyItem(
      name: 'DAY-HL Liquidity Sweep',
      source: 'quant/day_hl_liquidity.py',
      state: StrategyState.bundled,
      statusLine: 'Detector bundled • entry/exit/risk mapping still required',
      detail: 'Day-high / day-low liquidity event detector only.',
    ),
    _StrategyItem(
      name: 'Opening Range Breakout (ORB)',
      source: 'No verified standalone engine on main',
      state: StrategyState.notImplemented,
      statusLine: 'Not implemented on this release',
      detail:
          'Shown only when engine, tests and backend routing exist.',
    ),
    _StrategyItem(
      name: 'VWAP Strategy',
      source: 'Indicator output is not a strategy engine',
      state: StrategyState.notImplemented,
      statusLine: 'Not implemented on this release',
      detail:
          'Needs defined rules, stops, targets and backtest before activation.',
    ),
  ];

  @override
  Widget build(BuildContext context) => ListView(
        key: const ValueKey('strategy-library-list'),
        padding: const EdgeInsets.all(12),
        children: [
          const Text(
            'STRATEGY LIBRARY',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 6),
          const Text(
            'This is a research inventory, not a live signal board. '
            'Quant source files may be bundled in the repo; the APK does not run them locally. '
            'Actionable signals only come from the Railway API after 5-layer validation and the 10-minute stability gate.',
            style: TextStyle(color: Colors.white70, height: 1.35),
          ),
          const SizedBox(height: 12),
          for (final item in _items) _StrategyCard(item: item),
          const SizedBox(height: 8),
          const Card(
            child: Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                'Safety: inventory only — not a signal generator. '
                'Until a strategy is connected end-to-end and validated, it stays non-actionable. '
                'No win rate or profitability is implied.',
                style: TextStyle(fontWeight: FontWeight.w700, height: 1.35),
              ),
            ),
          ),
        ],
      );
}

enum StrategyState { bundled, notImplemented }

class _StrategyItem {
  const _StrategyItem({
    required this.name,
    required this.source,
    required this.state,
    required this.statusLine,
    required this.detail,
  });

  final String name;
  final String source;
  final StrategyState state;
  final String statusLine;
  final String detail;
}

class _StrategyCard extends StatelessWidget {
  const _StrategyCard({required this.item});

  final _StrategyItem item;

  @override
  Widget build(BuildContext context) {
    final bundled = item.state == StrategyState.bundled;
    final badgeColor =
        bundled ? const Color(0xFF38BDF8) : const Color(0xFF94A3B8);
    final statusColor =
        bundled ? const Color(0xFFFBBF24) : const Color(0xFF94A3B8);
    final badgeText = bundled ? 'SOURCE BUNDLED' : 'NOT IMPLEMENTED';

    return Card(
      margin: const EdgeInsets.only(bottom: 9),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    item.name,
                    style: const TextStyle(
                      fontWeight: FontWeight.w900,
                      fontSize: 16,
                    ),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: badgeColor.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    badgeText,
                    style: TextStyle(
                      color: badgeColor,
                      fontWeight: FontWeight.w900,
                      fontSize: 10,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 7),
            Text(item.detail, style: const TextStyle(height: 1.35)),
            const SizedBox(height: 7),
            Text(
              'Source: ${item.source}',
              style: const TextStyle(fontSize: 11, color: Colors.white60),
            ),
            const SizedBox(height: 4),
            Text(
              item.statusLine,
              style: TextStyle(
                fontSize: 12,
                color: statusColor,
                fontWeight: FontWeight.w700,
                height: 1.3,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
