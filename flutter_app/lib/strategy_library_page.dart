import 'package:flutter/material.dart';

/// Makes the strategy inventory visible without falsely presenting source files
/// as live, validated or order-ready strategies.
class StrategyLibraryPage extends StatelessWidget {
  const StrategyLibraryPage({super.key});

  static const _items = <_StrategyItem>[
    _StrategyItem(
      name: 'OI Price Action',
      source: 'quant/oi_price_action_engine.py',
      state: 'ENGINE SOURCE PRESENT',
      live: 'Live API wiring not verified',
      detail: 'Uses option-chain OI/PCR, price structure and candle/ATR confluence. Missing/stale OI data must return WAIT.',
    ),
    _StrategyItem(
      name: 'Hero Zero',
      source: 'quant/hero_zero.py',
      state: 'ENGINE SOURCE PRESENT',
      live: 'Expiry-only candidate; live API wiring not verified',
      detail: 'High-risk expiry-day setup with time-window and premium guards. Candidate only; never an order approval.',
    ),
    _StrategyItem(
      name: 'Failed-Move / PDH-PDL',
      source: 'quant/failed_move_fade.py',
      state: 'ENGINE SOURCE PRESENT',
      live: 'Live API wiring not verified',
      detail: 'Detects acceptance beyond previous-day high/low. Stale candles or failed validation must result in WAIT.',
    ),
    _StrategyItem(
      name: 'EMA Crossover',
      source: 'quant/ema_quant_engine.py',
      state: 'ENGINE SOURCE PRESENT',
      live: 'Live API wiring not verified',
      detail: 'EMA trend candidate with RSI/ATR filters. Must be merged, connected to the backend and tested before live use.',
    ),
    _StrategyItem(
      name: 'DAY-HL Liquidity Sweep',
      source: 'quant/day_hl_liquidity.py',
      state: 'DETECTOR SOURCE PRESENT',
      live: 'Detector only; live API wiring not verified',
      detail: 'Day-high/day-low liquidity event detector. Needs confirmed entry, invalidation, exit and risk mapping.',
    ),
    _StrategyItem(
      name: 'Opening Range Breakout (ORB)',
      source: 'quant/orb_engine.py',
      state: 'ENGINE SOURCE PRESENT',
      live: 'Candidate engine added; live API wiring not verified',
      detail: '15-minute opening-range breakout with completed-candle and volume checks plus ATR risk levels. Candidate only until backend routing and live-data validation are proven.',
    ),
    _StrategyItem(
      name: 'VWAP Strategy',
      source: 'quant/vwap_strategy.py',
      state: 'ENGINE SOURCE PRESENT',
      live: 'Candidate engine added; live API wiring not verified',
      detail: 'Session-reset VWAP cross with volume confirmation and ATR-based stop/target. Candidate only until backend routing and live-data validation are proven.',
    ),
  ];

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('STRATEGY LIBRARY', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
      const SizedBox(height: 6),
      const Text(
        'Source presence is not live integration. The five listed strategy/detector sources are not executed by Flutter itself: live APK signals require verified backend routing, fresh-data checks, risk validation and the 10-minute stability gate.',
        style: TextStyle(color: Colors.white70),
      ),
      const SizedBox(height: 12),
      for (final item in _items) _StrategyCard(item: item),
      const SizedBox(height: 8),
      const Card(
        child: Padding(
          padding: EdgeInsets.all(12),
          child: Text(
            'Safety: this page is an inventory, not a signal generator. Until a strategy is connected end-to-end and validated, it must remain non-actionable. Missing/stale data, failed risk checks or incomplete stability confirmation must keep the signal at WAIT. No win rate or profitability is implied.',
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
    final sourcePresent = item.state == 'ENGINE SOURCE PRESENT' || item.state == 'DETECTOR SOURCE PRESENT';
    final color = sourcePresent ? Colors.orangeAccent : Colors.redAccent;
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
