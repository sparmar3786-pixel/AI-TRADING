import 'package:flutter/material.dart';

/// Inventory only: each strategy appears exactly once. Backend candidate data
/// is displayed inside its matching inventory card and never creates a second
/// parallel card/list. Missing or stale data remains WAIT/non-actionable.
class StrategyLibraryPage extends StatelessWidget {
  const StrategyLibraryPage({
    this.signals = const {},
    this.selectedIndex = 'NIFTY',
    super.key,
  });

  final Map<String, dynamic> signals;
  final String selectedIndex;

  static const _items = <_StrategyItem>[
    _StrategyItem(
      keyName: 'oi_price_action',
      cardKey: 'candidate-card-oi-price-action',
      name: 'OI Price Action',
      source: 'quant/oi_price_action_engine.py',
      state: 'CANDIDATE PIPELINE • WAIT-GATED',
      live: 'Option mapping, risk and 600-second gate are still required',
      detail: 'Uses option-chain OI/PCR, price structure and candle/ATR confluence. Missing or stale OI data must return WAIT.',
    ),
    _StrategyItem(
      keyName: 'hero_zero',
      cardKey: 'candidate-card-hero-zero',
      name: 'Hero Zero',
      source: 'quant/hero_zero.py',
      state: 'CANDIDATE PIPELINE • WAIT-GATED',
      live: 'Expiry and fresh option quotes required; candidate is not actionable',
      detail: 'High-risk expiry-day setup with time-window and premium guards. Candidate only; never an order approval.',
    ),
    _StrategyItem(
      keyName: 'failed_move_pdh_pdl',
      cardKey: 'candidate-card-failed-move-pdh-pdl',
      name: 'Failed-Move / PDH-PDL',
      source: 'quant/failed_move_fade.py',
      state: 'CANDIDATE PIPELINE • WAIT-GATED',
      live: 'Contract mapping, risk and stability checks remain required',
      detail: 'Detects failed acceptance beyond previous-day high/low. Stale candles or failed validation must result in WAIT.',
    ),
    _StrategyItem(
      keyName: 'ema_crossover',
      cardKey: 'candidate-card-ema-crossover',
      name: 'EMA Crossover',
      source: 'quant/ema_quant_engine.py',
      state: 'CANDIDATE PIPELINE • WAIT-GATED',
      live: 'EMA setup cannot bypass Quant or risk gates',
      detail: 'EMA trend candidate with RSI/ATR filters. Backend routing and live-data validation must pass before use.',
    ),
    _StrategyItem(
      keyName: 'day_hl_liquidity_sweep',
      cardKey: 'candidate-card-day-hl-liquidity-sweep',
      name: 'DAY-HL Liquidity Sweep',
      source: 'quant/day_hl_liquidity.py',
      state: 'DETECTOR ONLY • WAIT-GATED',
      live: 'Sweep evidence only; complete entry, exit and risk mapping is not implemented',
      detail: 'Day-high/day-low liquidity event detector. Requires confirmed entry, invalidation, exit and risk mapping.',
    ),
    _StrategyItem(
      keyName: 'orb',
      cardKey: 'candidate-card-orb',
      name: 'Opening Range Breakout (ORB)',
      source: 'quant/orb_engine.py',
      state: 'CANDIDATE PIPELINE • WAIT-GATED',
      live: 'Contract, risk and stability gates remain required',
      detail: '15-minute opening-range breakout with completed-candle and volume checks plus ATR risk levels. Candidate only until live validation is proven.',
    ),
    _StrategyItem(
      keyName: 'vwap',
      cardKey: 'candidate-card-vwap',
      name: 'VWAP Strategy',
      source: 'quant/vwap_strategy.py',
      state: 'CANDIDATE PIPELINE • WAIT-GATED',
      live: 'Contract, risk and stability gates remain required',
      detail: 'Session-reset VWAP cross with volume confirmation and ATR-based stop/target. Candidate only until live validation is proven.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final signal = Map<String, dynamic>.from(
      signals[selectedIndex] as Map? ?? const {},
    );
    final candidates = Map<String, dynamic>.from(
      signal['strategy_candidates'] as Map? ?? const {},
    );

    return ListView(
      key: const ValueKey('parmar-strategy-list'),
      padding: const EdgeInsets.all(12),
      children: [
        const Text(
          'STRATEGY LIBRARY',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 6),
        const Text(
          'Each strategy is shown once. Candidate details come from the canonical backend /v1/signals strategy_candidates payload. A candidate is not an approved trade: fresh data, option-contract mapping, five-layer Quant, risk checks and the server-owned 600-second stability gate must pass. DAY-HL is detector-only.',
          style: TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 12),
        for (final item in _items)
          _StrategyCard(
            key: ValueKey(item.cardKey),
            item: item,
            candidate: Map<String, dynamic>.from(
              candidates[item.keyName] as Map? ?? const {},
            ),
          ),
        const SizedBox(height: 8),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(12),
            child: Text(
              'Safety: this page is an inventory, not a signal generator. Until a strategy is connected end-to-end and validated, it remains non-actionable. Missing/stale data, failed risk checks or incomplete stability confirmation must keep the signal at WAIT. No win rate or profitability is implied.',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
        ),
      ],
    );
  }
}

class _StrategyItem {
  const _StrategyItem({
    required this.keyName,
    required this.cardKey,
    required this.name,
    required this.source,
    required this.state,
    required this.live,
    required this.detail,
  });

  final String keyName;
  final String cardKey;
  final String name;
  final String source;
  final String state;
  final String live;
  final String detail;
}

class _StrategyCard extends StatelessWidget {
  const _StrategyCard({
    super.key,
    required this.item,
    required this.candidate,
  });

  final _StrategyItem item;
  final Map<String, dynamic> candidate;

  @override
  Widget build(BuildContext context) {
    final direction = (candidate['candidate_decision'] ?? 'WAIT').toString();
    final approved = (candidate['decision'] ?? 'WAIT').toString();
    final fresh = candidate['data_fresh'] == true;
    final reasons = (candidate['reasons'] as List? ?? const [])
        .map((value) => value.toString())
        .toList();
    final guards = (candidate['guards'] as List? ?? const [])
        .map((value) => value.toString())
        .toList();
    final validation = Map<String, dynamic>.from(
      candidate['live_validation'] as Map? ?? const {},
    );
    final blocks = (validation['blocks'] as List? ?? const [])
        .map((value) => value.toString())
        .toList();
    String value(dynamic raw) => raw == null ? '—' : raw.toString();
    final statusColor = fresh ? Colors.greenAccent : Colors.orangeAccent;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Keep the title and status on separate lines. Long labels must
            // wrap instead of squeezing/overlapping the strategy title.
            Text(
              item.name,
              softWrap: true,
              style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
            ),
            const SizedBox(height: 5),
            Wrap(
              spacing: 6,
              runSpacing: 5,
              children: [
                _StatusPill(
                  label: fresh ? 'FRESH INPUT' : 'DATA REQUIRED',
                  color: statusColor,
                ),
                _StatusPill(
                  label: item.state,
                  color: Colors.orangeAccent,
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(item.detail, softWrap: true),
            const SizedBox(height: 7),
            Text(
              'Candidate: $direction  •  Approved decision: $approved',
              softWrap: true,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 4),
            Text(
              'Underlying entry: ${value(candidate['entry'])}  •  SL: ${value(candidate['stop_loss'])}  •  Target: ${value(candidate['target'])}',
              key: ValueKey('candidate-levels-${item.keyName}'),
              softWrap: true,
              style: const TextStyle(fontSize: 12, color: Colors.white70),
            ),
            const SizedBox(height: 5),
            Text(
              'Reason: ${reasons.isEmpty ? 'No candidate result returned by backend.' : reasons.join(' • ')}',
              softWrap: true,
              style: const TextStyle(fontSize: 11, color: Colors.white70),
            ),
            if (blocks.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                'Blocked by: ${blocks.join(' • ')}',
                softWrap: true,
                style: const TextStyle(fontSize: 11, color: Colors.orangeAccent),
              ),
            ],
            if (guards.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                'Guards: ${guards.join(' • ')}',
                softWrap: true,
                style: const TextStyle(fontSize: 10, color: Colors.white54),
              ),
            ],
            const SizedBox(height: 5),
            Text(
              'Source: ${item.source}',
              softWrap: true,
              style: const TextStyle(fontSize: 11, color: Colors.white60),
            ),
            const SizedBox(height: 4),
            Text(
              item.live,
              softWrap: true,
              style: TextStyle(
                fontSize: 12,
                color: statusColor,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 4),
            const Text(
              'Underlying spot levels only—not option-premium prices. Candidate is never actionable from this card.',
              softWrap: true,
              style: TextStyle(fontSize: 10, color: Colors.orangeAccent),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
        constraints: const BoxConstraints(maxWidth: 320),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
        decoration: BoxDecoration(
          color: color.withOpacity(0.13),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(
          label,
          softWrap: true,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w900,
            fontSize: 10,
          ),
        ),
      );
}
