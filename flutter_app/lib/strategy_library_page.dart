import 'package:flutter/material.dart';

/// Makes the strategy inventory visible without falsely presenting source files
/// as live, validated or order-ready strategies.
class StrategyLibraryPage extends StatelessWidget {
  const StrategyLibraryPage({super.key});

  static const _items = <_StrategyItem>[
    _StrategyItem(
      name: 'OI Price Action',
      source: 'quant/oi_price_action_engine.py',
      state: 'SOURCE BUNDLED',
      live: 'Live API wiring not verified',
      detail: 'Uses option-chain OI/PCR, price structure and candle/ATR confluence. Missing/stale OI data must return WAIT.',
    ),
    _StrategyItem(
      name: 'Hero Zero',
      source: 'quant/hero_zero.py',
      state: 'SOURCE BUNDLED',
      live: 'Expiry-only candidate; live API wiring not verified',
      detail: 'High-risk expiry-day setup with time-window and premium guards. Candidate only; never an order approval.',
    ),
    _StrategyItem(
      name: 'Failed-Move / PDH-PDL',
      source: 'quant/failed_move_fade.py',
      state: 'SOURCE BUNDLED',
      live: 'Live API wiring not verified',
      detail: 'Detects acceptance beyond previous-day high/low. Stale candles or failed validation must result in WAIT.',
    ),
    _StrategyItem(
      name: 'EMA Crossover',
      source: 'quant/ema_quant_engine.py',
      state: 'SOURCE BUNDLED',
      live: 'Live API wiring not verified',
      detail: 'EMA trend candidate with RSI/ATR filters. Must be merged, connected to the backend and tested before live use.',
    ),
    _StrategyItem(
      name: 'DAY-HL Liquidity Sweep',
      source: 'quant/day_hl_liquidity.py',
      state: 'SOURCE BUNDLED',
      live: 'Detector only; live API wiring not verified',
      detail: 'Day-high/day-low liquidity event detector. Needs confirmed entry, invalidation, exit and risk mapping.',
    ),
    _StrategyItem(
      name: 'Opening Range Breakout (ORB)',
      source: 'No verified standalone engine on main',
      state: 'NOT IMPLEMENTED',
      live: 'Not active; no verified engine source',
      detail: 'Must not be presented as active until implementation, tests and backend routing are present.',
    ),
    _StrategyItem(
      name: 'VWAP Strategy',
      source: 'Indicator output is not a strategy engine',
      state: 'NOT IMPLEMENTED',
      live: 'Not active; indicator does not prove entry/exit integration',
      detail: 'Requires defined trend/mean-reversion rules, stops, targets and backtest validation.',
    ),
  ];

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('STRATEGY LIBRARY', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
      const SizedBox(height: 6),
      const Text(
        'Five strategy-engine source files are included in this release branch. They are not executed by Flutter itself: live APK signals still require backend routing, fresh-data checks and risk validation.',
        style: TextStyle(color: Colors.white70),
      ),
      const SizedBox(height: 12),
      for (final item in _items) _StrategyCard(item: item),
      const SizedBox(height: 8),
      const Card(
        child: Padding(
          padding: EdgeInsets.all(12),
          child: Text(
            'Safety: this page is an inventory, not a signal generator. Until a strategy is connected end-to-end and validated, it must remain non-actionable. No win rate or profitability is implied.',
            style: TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
      ),
    ],
  );
}

class _StrategyItem {
  const _StrategyItem({
    required this.name,
    required this.source,
    required this.state,
    required this.live,
    required this.detail,
  });
  final String name;
  final String source;
  final String state;
  final String live;
  final String detail;
}

class _StrategyCard extends StatelessWidget {
  const _StrategyCard({required this.item});
  final _StrategyItem item;

  @override
  Widget build(BuildContext context) {
    final ready = item.state == 'SOURCE BUNDLED';
    final color = ready ? Colors.orangeAccent : Colors.redAccent;
    return Card(
      margin: const EdgeInsets.only(bottom: 9),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(item.name, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16))),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(color: color.withOpacity(0.13), borderRadius: BorderRadius.circular(6)),
                  child: Text(item.state, style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 10)),
                ),
              ],
            ),
            const SizedBox(height: 7),
            Text(item.detail),
            const SizedBox(height: 7),
            Text('Source: ${item.source}', style: const TextStyle(fontSize: 11, color: Colors.white60)),
            const SizedBox(height: 4),
            Text(item.live, style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w700)),
          ],
        ),
      ),
    );
  }
}
