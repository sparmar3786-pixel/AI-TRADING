import 'package:flutter/material.dart';
import 'api.dart';

/// Parmar strategy suite inventory. A listed strategy is not automatically live/actionable.
class StrategyLibraryPage extends StatelessWidget {
  const StrategyLibraryPage({super.key, this.index = 'NIFTY'});
  final String index;

  static const _items = <_StrategyItem>[
    _StrategyItem(
      id: 'oi_price_action',
      key: 'strategy-card-oi-price-action',
      name: 'OI Price Action',
      source: 'quant/oi_price_action_engine.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Canonical signal candidate; option mapping, risk and stability remain unverified',
      detail: 'Uses option-chain OI/PCR, price structure and candle/ATR confluence. Missing/stale OI data must return WAIT.',
    ),
    _StrategyItem(
      id: 'hero_zero',
      key: 'strategy-card-hero-zero',
      name: 'Hero Zero',
      source: 'quant/hero_zero.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Expiry and fresh option quotes required; no actionable signal is implied',
      detail: 'High-risk expiry-day setup with time-window and premium guards. Candidate only; never an order approval.',
    ),
    _StrategyItem(
      id: 'failed_move_pdh_pdl',
      key: 'strategy-card-failed-move-pdh-pdl',
      name: 'Failed-Move / PDH-PDL',
      source: 'quant/failed_move_fade.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Canonical candidate; option mapping, risk and stability remain unverified',
      detail: 'Detects acceptance beyond previous-day high/low. Stale candles or failed validation must result in WAIT.',
    ),
    _StrategyItem(
      id: 'ema_crossover',
      key: 'strategy-card-ema-crossover',
      name: 'EMA Crossover',
      source: 'quant/ema_quant_engine.py',
      state: 'SOURCE BUNDLED',
      live: 'Live API wiring not verified',
      detail: 'EMA trend candidate with RSI/ATR filters. Must be merged, connected to the backend and tested before live use.',
    ),
    _StrategyItem(
      id: 'day_hl_liquidity_sweep',
      key: 'strategy-card-day-hl-liquidity-sweep',
      name: 'DAY-HL Liquidity Sweep',
      source: 'quant/day_hl_liquidity.py',
      state: 'DETECTOR PIPELINE WIRED • WAIT-GATED',
      live: 'Sweep evidence only; full option/risk mapping is not implemented',
      detail: 'Day-high/day-low liquidity event detector. Needs confirmed entry, invalidation, exit and risk mapping.',
    ),
    _StrategyItem(
      id: 'orb',
      key: 'strategy-card-orb',
      name: 'Opening Range Breakout (ORB)',
      source: 'quant/orb_engine.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Candidate path exists; full live option/risk/confirmation certification remains pending',
      detail: 'Must not be presented as active until implementation, tests and backend routing are present.',
    ),
    _StrategyItem(
      id: 'vwap',
      key: 'strategy-card-vwap',
      name: 'VWAP Strategy',
      source: 'quant/vwap_strategy.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Candidate path exists; full live option/risk/confirmation certification remains pending',
      detail: 'Requires defined trend/mean-reversion rules, stops, targets and backtest validation.',
    ),
  ];

  @override
  Widget build(BuildContext context) => ListView(
    key: const ValueKey('strategy-library-list'),
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
      for (final item in _items) _StrategyCard(key: ValueKey(item.key), item: item, index: index),
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
    required this.id,
    required this.key,
    required this.name,
    required this.source,
    required this.state,
    required this.live,
    required this.detail,
  });
  final String id;
  final String key;
  final String name;
  final String source;
  final String state;
  final String live;
  final String detail;
}

class _StrategyCard extends StatelessWidget {
  const _StrategyCard({super.key, required this.item, required this.index});
  final _StrategyItem item;
  final String index;

  @override
  Widget build(BuildContext context) {
    final color = item.state.contains('WIRED') ? Colors.orangeAccent : Colors.redAccent;
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
            const SizedBox(height: 10),
            FutureBuilder<Map<String, dynamic>>(
              future: FreshApi.signal().evaluateParmarStrategy(strategyId: item.id, index: index),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Text('Live candidate: checking canonical signal payload…',
                      style: TextStyle(fontSize: 12, color: Colors.white70));
                }
                if (snapshot.hasError) {
                  return const Text('Live candidate unavailable • WAIT • not actionable',
                      style: TextStyle(fontSize: 12, color: Colors.orangeAccent));
                }
                final data = snapshot.data ?? const <String, dynamic>{};
                final candidate = Map<String, dynamic>.from(
                    data['candidate_snapshot'] as Map? ?? const <String, dynamic>{});
                final checks = Map<String, dynamic>.from(
                    data['checks'] as Map? ?? const <String, dynamic>{});
                final candidateDecision = (data['candidate_decision'] ?? 'NONE').toString();
                final entry = candidate['entry'];
                final stop = candidate['stop_loss'];
                final target = candidate['target'];
                final reasons = (candidate['reasons'] as List? ?? const <dynamic>[])
                    .map((value) => value.toString()).take(2).join(' • ');
                final guards = (data['guards'] as List? ?? const <dynamic>[])
                    .map((value) => value.toString()).take(3).join(' • ');
                return Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(9),
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white12),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Backend decision: WAIT • Actionable: NO',
                          style: TextStyle(fontWeight: FontWeight.w900, color: Colors.orangeAccent)),
                      Text('Candidate: $candidateDecision • ${checks['fresh_live_market_data'] == true ? 'market data fresh' : 'market freshness not verified'}',
                          style: const TextStyle(fontSize: 12)),
                      if (entry != null || stop != null || target != null)
                        Text('Underlying spot levels only — Entry: ${entry ?? '—'} • SL: ${stop ?? '—'} • Target: ${target ?? '—'}',
                            style: const TextStyle(fontSize: 11, color: Colors.white70)),
                      if (reasons.isNotEmpty)
                        Text(reasons, style: const TextStyle(fontSize: 11, color: Colors.white70)),
                      if (guards.isNotEmpty)
                        Text('Blockers: $guards', style: const TextStyle(fontSize: 11, color: Colors.orangeAccent)),
                    ],
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
