import 'package:flutter/material.dart';
import 'api.dart';

/// Parmar strategy suite inventory. A listed strategy is not automatically live/actionable.
class StrategyLibraryPage extends StatelessWidget {
  const StrategyLibraryPage({super.key});

  static const _items = <_StrategyItem>[
    _StrategyItem(
      name: 'OI Price Action',
      source: 'quant/oi_price_action_engine.py',
      state: 'ENGINE SOURCE PRESENT',
      live: 'Backend adapter / live wiring must be verified',
      detail: 'Uses option-chain OI/PCR, price structure and candle/ATR confluence. Missing/stale OI data must return WAIT.',
    ),
    _StrategyItem(
      name: 'Hero Zero',
      source: 'quant/hero_zero.py',
      state: 'ENGINE SOURCE PRESENT',
      live: 'Expiry-only; backend adapter / live wiring must be verified',
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
      state: 'DETECTOR SOURCE PRESENT',
      live: 'Detector only; backend adapter and risk mapping must be verified',
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
      const Text('PARMAR STRATEGY ENGINE', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
      const SizedBox(height: 6),
      FutureBuilder<Map<String, dynamic>>(
        future: FreshApi.signal().parmarStrategies(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Card(child: Padding(
              padding: EdgeInsets.all(10),
              child: Text('Parmar backend: checking…'),
            ));
          }
          if (snapshot.hasError) {
            return Card(child: Padding(
              padding: const EdgeInsets.all(10),
              child: Text('Parmar backend unavailable: ${snapshot.error}',
                  style: const TextStyle(color: Colors.orangeAccent)),
            ));
          }
          final data = snapshot.data ?? const <String, dynamic>{};
          final count = data['count'] ?? 0;
          return Card(child: Padding(
            padding: const EdgeInsets.all(10),
            child: Text('Parmar backend connected • ${count.toString()} strategies listed. Evaluation remains WAIT until verified adapters and live-data validation are wired.',
                style: const TextStyle(color: Colors.lightGreenAccent)),
          ));
        },
      ),
      const Text(
        'Separate strategy suite: Price Action / OI Price Action, Hero Zero, Failed Move / PDH-PDL, EMA Crossover, Day HL Liquidity Sweep, ORB and VWAP. The backend orchestrator is fail-closed; only registered and tested adapters can evaluate. All candidates still require fresh-data, risk and 10-minute stability gates.',
        style: TextStyle(color: Colors.white70),
      ),
      const SizedBox(height: 12),
      for (final item in _items) _StrategyCard(item: item),
      const SizedBox(height: 8),
      const Card(
        child: Padding(
          padding: EdgeInsets.all(12),
          child: Text(
            'Safety: this page lists the Parmar engine suite. The registry never upgrades WAIT to BUY/SELL; unregistered adapters and missing/stale data remain WAIT. ORB and VWAP remain NOT IMPLEMENTED until their own tested engines are added. No win rate or profitability is implied.',
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
    final ready = item.state.contains('SOURCE PRESENT');
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
