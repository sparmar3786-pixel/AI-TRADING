import 'package:flutter/material.dart';

/// Makes the strategy inventory visible without falsely presenting source files
/// as live, validated or order-ready strategies.
class StrategyLibraryPage extends StatelessWidget {
  const StrategyLibraryPage({this.signals = const {}, this.selectedIndex = 'NIFTY', super.key});

  final Map<String, dynamic> signals;
  final String selectedIndex;

  static const _items = <_StrategyItem>[
    _StrategyItem(
      name: 'OI Price Action',
      source: 'quant/oi_price_action_engine.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Canonical candidate; option mapping, risk and 600-second gate still required',
      detail: 'Uses option-chain OI/PCR, price structure and candle/ATR confluence. Missing/stale OI data must return WAIT.',
    ),
    _StrategyItem(
      name: 'Hero Zero',
      source: 'quant/hero_zero.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Expiry and fresh option quotes required; candidate is not actionable',
      detail: 'High-risk expiry-day setup with time-window and premium guards. Candidate only; never an order approval.',
    ),
    _StrategyItem(
      name: 'Failed-Move / PDH-PDL',
      source: 'quant/failed_move_fade.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Canonical candidate; contract mapping, risk and stability still gated',
      detail: 'Detects acceptance beyond previous-day high/low. Stale candles or failed validation must result in WAIT.',
    ),
    _StrategyItem(
      name: 'EMA Crossover',
      source: 'quant/ema_quant_engine.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Canonical candidate; EMA setup does not bypass Quant or risk gates',
      detail: 'EMA trend candidate with RSI/ATR filters. Must be merged, connected to the backend and tested before live use.',
    ),
    _StrategyItem(
      name: 'DAY-HL Liquidity Sweep',
      source: 'quant/day_hl_liquidity.py',
      state: 'DETECTOR PIPELINE WIRED • WAIT-GATED',
      live: 'Sweep evidence only; complete option/risk mapping is not implemented',
      detail: 'Day-high/day-low liquidity event detector. Needs confirmed entry, invalidation, exit and risk mapping.',
    ),
    _StrategyItem(
      name: 'Opening Range Breakout (ORB)',
      source: 'quant/orb_engine.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Shared signal candidate; contract/risk/stability gates remain required',
      detail: '15-minute opening-range breakout with completed-candle and volume checks plus ATR risk levels. Candidate only until backend routing and live-data validation are proven.',
    ),
    _StrategyItem(
      name: 'VWAP Strategy',
      source: 'quant/vwap_strategy.py',
      state: 'CANDIDATE PIPELINE WIRED • WAIT-GATED',
      live: 'Shared signal candidate; contract/risk/stability gates remain required',
      detail: 'Session-reset VWAP cross with volume confirmation and ATR-based stop/target. Candidate only until backend routing and live-data validation are proven.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final signal = Map<String, dynamic>.from(signals[selectedIndex] as Map? ?? const {});
    final candidates = Map<String, dynamic>.from(signal['strategy_candidates'] as Map? ?? const {});
    return ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('STRATEGY LIBRARY', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
      const SizedBox(height: 6),
      const Text(
        'All seven candidates are read from the canonical backend /v1/signals strategy_candidates payload. A candidate is not an approved trade: option-contract mapping, five-layer Quant, risk checks and the server-owned 600-second stability gate must pass. DAY-HL is detector-only.',
        style: TextStyle(color: Colors.white70),
      ),
      const SizedBox(height: 12),
      _CandidateCard(key: const ValueKey('candidate-card-oi-price-action'), title: 'OI Price Action', candidate: Map<String, dynamic>.from(candidates['oi_price_action'] as Map? ?? const {})),
      _CandidateCard(key: const ValueKey('candidate-card-hero-zero'), title: 'Hero Zero', candidate: Map<String, dynamic>.from(candidates['hero_zero'] as Map? ?? const {})),
      _CandidateCard(key: const ValueKey('candidate-card-failed-move-pdh-pdl'), title: 'Failed-Move / PDH-PDL', candidate: Map<String, dynamic>.from(candidates['failed_move_pdh_pdl'] as Map? ?? const {})),
      _CandidateCard(key: const ValueKey('candidate-card-ema-crossover'), title: 'EMA Crossover', candidate: Map<String, dynamic>.from(candidates['ema_crossover'] as Map? ?? const {})),
      _CandidateCard(key: const ValueKey('candidate-card-day-hl-liquidity-sweep'), title: 'DAY-HL Liquidity Sweep', candidate: Map<String, dynamic>.from(candidates['day_hl_liquidity_sweep'] as Map? ?? const {})),
      _CandidateCard(key: const ValueKey('candidate-card-orb'), title: 'Opening Range Breakout (ORB)', candidate: Map<String, dynamic>.from(candidates['orb'] as Map? ?? const {})),
      _CandidateCard(key: const ValueKey('candidate-card-vwap'), title: 'VWAP Strategy', candidate: Map<String, dynamic>.from(candidates['vwap'] as Map? ?? const {})),
      const SizedBox(height: 4),
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
}

class _CandidateCard extends StatelessWidget {
  const _CandidateCard({super.key, required this.title, required this.candidate});
  final String title;
  final Map<String, dynamic> candidate;

  @override
  Widget build(BuildContext context) {
    final direction = (candidate['candidate_decision'] ?? 'WAIT').toString();
    final approved = (candidate['decision'] ?? 'WAIT').toString();
    final fresh = candidate['data_fresh'] == true;
    final reasons = (candidate['reasons'] as List? ?? const []).map((v) => v.toString()).toList();
    final guards = (candidate['guards'] as List? ?? const []).map((v) => v.toString()).toList();
    final validation = Map<String, dynamic>.from(candidate['live_validation'] as Map? ?? const {});
    final blocks = (validation['blocks'] as List? ?? const []).map((v) => v.toString()).toList();
    String value(dynamic raw) => raw == null ? '—' : raw.toString();
    return Card(
      margin: const EdgeInsets.only(bottom: 9),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(title, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15))),
            Text(fresh ? 'FRESH INPUT' : 'DATA REQUIRED',
              style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900,
                color: fresh ? Colors.greenAccent : Colors.orangeAccent)),
          ]),
          const SizedBox(height: 6),
          Text('Candidate: $direction • Approved decision: $approved',
            style: const TextStyle(fontWeight: FontWeight.w800)),
          Text('Underlying entry: ${value(candidate['entry'])} • SL: ${value(candidate['stop_loss'])} • Target: ${value(candidate['target'])}',
            style: const TextStyle(fontSize: 12, color: Colors.white70)),
          const SizedBox(height: 5),
          Text('Reason: ${reasons.isEmpty ? 'No candidate result returned by backend.' : reasons.join(' • ')}',
            style: const TextStyle(fontSize: 11, color: Colors.white70)),
          if (blocks.isNotEmpty)
            Text('Blocked by: ${blocks.join(' • ')}', style: const TextStyle(fontSize: 11, color: Colors.orangeAccent)),
          if (guards.isNotEmpty)
            Text('Guards: ${guards.join(' • ')}', style: const TextStyle(fontSize: 10, color: Colors.white54)),
          const SizedBox(height: 4),
          const Text('Underlying spot levels only—not option-premium prices. Candidate is never actionable from this card.',
            style: TextStyle(fontSize: 10, color: Colors.orangeAccent)),
        ]),
      ),
    );
  }
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
    final sourcePresent = item.state.contains('WIRED') || item.state.contains('SOURCE PRESENT');
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
