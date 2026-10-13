import 'package:flutter/material.dart';

class StrategyLibraryPage extends StatefulWidget {
  const StrategyLibraryPage({required this.market, required this.signals, required this.selectedIndex, super.key});
  final Map<String, dynamic> market;
  final Map<String, dynamic> signals;
  final String selectedIndex;
  @override
  State<StrategyLibraryPage> createState() => _StrategyLibraryPageState();
}

Map<String, dynamic> marketRowFallback(Map<String, dynamic> market, String index) {
  final row = market[index];
  if (row is Map) return Map<String, dynamic>.from(row['strategy_suite'] as Map? ?? const {});
  return <String, dynamic>{};
}

class _StrategyLibraryPageState extends State<StrategyLibraryPage> {
  final search = TextEditingController();
  String category = 'All';
  static const items = <Map<String, String>>[
    {'name':'EMA Trend Following','group':'Trend','detail':'Fast/slow EMA crossover; confirm trend and avoid flat markets.','risk':'Trend confirmation + ATR stop'},
    {'name':'Donchian Breakout','group':'Trend','detail':'Breakout above/below a rolling channel; use only closed candles.','risk':'ATR stop + false-breakout filter'},
    {'name':'Time-Series Momentum','group':'Momentum','detail':'Compare return over a lookback window with zero; rank only after costs.','risk':'Volatility scaling + drawdown cap'},
    {'name':'RSI Mean Reversion','group':'Mean Reversion','detail':'Extreme RSI with a trend/regime filter; do not fade strong trends blindly.','risk':'Hard stop + time stop'},
    {'name':'Bollinger Band Reversion','group':'Mean Reversion','detail':'Band excursion followed by re-entry; require range-regime confirmation.','risk':'Regime filter + gap-risk handling'},
    {'name':'Pairs / Cointegration','group':'Statistical','detail':'Trade normalized spread deviations only after stationarity/cointegration checks.','risk':'Spread stop + hedge-ratio drift'},
    {'name':'Cross-Sectional Momentum','group':'Factor','detail':'Rank a liquid universe by trailing return; rebalance with turnover limits.','risk':'Liquidity + concentration limits'},
    {'name':'Value + Quality Factors','group':'Factor','detail':'Combine valuation and quality ranks; use point-in-time fundamentals.','risk':'Survivorship/look-ahead controls'},
    {'name':'Volatility Breakout','group':'Volatility','detail':'Trade expansion from compressed volatility with volume confirmation.','risk':'ATR sizing + event filter'},
    {'name':'Volume / Order-Flow Imbalance','group':'Order Flow','detail':'Use real bid/ask volume or trade-side classified prints; candle volume alone is not true order flow.','risk':'Freshness + spread + liquidity gates'},
    {'name':'VWAP Reversion / Trend','group':'Intraday','detail':'Price-vs-VWAP with trend and session filters; reset by exchange session.','risk':'Intraday hard stop + square-off'},
    {'name':'Opening Range Breakout','group':'Intraday','detail':'Breakout from a defined opening range; validate with volume and market breadth.','risk':'Gap filter + daily loss limit'},
    {'name':'Options Volatility / Greeks','group':'Options','detail':'Compare implied and realized volatility; include Greeks, spreads and expiry effects.','risk':'Defined-risk structures only; no naked assumptions'},
    {'name':'Portfolio Risk Parity','group':'Portfolio','detail':'Scale exposures by realized volatility and correlation, not equal rupee allocation alone.','risk':'Correlation shock + max exposure'},
    {'name':'Walk-Forward Strategy Selection','group':'Validation','detail':'Tune on rolling train windows and evaluate on untouched forward windows.','risk':'No test-set tuning; multiple-testing penalty'},
  ];
  @override
  void dispose() { search.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final filtered = items.where((x) => (category == 'All' || x['group'] == category) && ('${x['name']} ${x['detail']} ${x['group']}'.toLowerCase().contains(search.text.toLowerCase()))).toList();
    final groups = ['All', ...items.map((x) => x['group']!).toSet()];
    final marketRow = Map<String, dynamic>.from(widget.market[widget.selectedIndex] as Map? ?? const {});
    final signalRow = Map<String, dynamic>.from(widget.signals[widget.selectedIndex] as Map? ?? const {});
    final layers = Map<String, dynamic>.from(signalRow['layers'] as Map? ?? const {});
    final passedLayers = layers.values.whereType<Map>().where((layer) => layer['pass'] == true).length;
    final suite = Map<String, dynamic>.from(signalRow['strategy_suite'] as Map? ?? marketRowFallback(widget.market, widget.selectedIndex));
    final suiteStrategies = Map<String, dynamic>.from(suite['strategies'] as Map? ?? const {});
    final suiteVotes = Map<String, dynamic>.from(suite['votes'] as Map? ?? const {});
    final fresh = marketRow['live'] == true;
    final ltp = marketRow['ltp'];
    return Scaffold(
      backgroundColor: const Color(0xFF070B12),
      body: SafeArea(child: ListView(padding: const EdgeInsets.all(14), children: [
        const Text('STRATEGY & QUANT LIBRARY', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, letterSpacing: 1)),
        const SizedBox(height: 6),
        const Text('Strategy catalogue • each strategy requires fresh data validation and backtesting before use.', style: TextStyle(color: Colors.white70)),
        const SizedBox(height: 12),
        Card(color: const Color(0xFF101722), child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('LIVE ENGINE CONTEXT • ${widget.selectedIndex}', style: const TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF12D6FF))),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: Text('Spot LTP: ${ltp == null ? '—' : ltp.toString()}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800))),
              Text(fresh ? 'FRESH QUOTE' : 'WAIT / STALE', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: fresh ? Colors.greenAccent : Colors.orangeAccent)),
            ]),
            const SizedBox(height: 5),
            Text('Signal: ${signalRow['decision'] ?? 'WAIT'} • Layers passed: $passedLayers / ${layers.length}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
            Text('Strategy consumption: ${suiteStrategies.length} outputs • LONG votes ${suiteVotes['LONG'] ?? 0} • SHORT votes ${suiteVotes['SHORT'] ?? 0} • status ${suite['status'] ?? 'NOT RETURNED'}',
              style: const TextStyle(color: Color(0xFF12D6FF), fontSize: 11, fontWeight: FontWeight.w700)),
            if (suiteStrategies.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text('EXECUTION TRACE UNAVAILABLE • backend returned no per-strategy outputs. Catalogue entries below are not execution evidence.',
                  style: TextStyle(color: Colors.orangeAccent, fontSize: 11, fontWeight: FontWeight.w700)),
              )
            else ...suiteStrategies.entries.map((entry) {
              final value = entry.value;
              final details = value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{'signal': value};
              final trace = details['trace'] is Map
                  ? Map<String, dynamic>.from(details['trace'] as Map)
                  : <String, dynamic>{};
              final signal = details['signal'] ?? details['decision'] ?? details['direction'] ?? 'NOT RETURNED';
              final score = details['score'] ?? details['confidence'] ?? details['alignment_score'] ?? '—';
              final reason = details['reason'] ?? details['reason_code'] ?? details['rejection_reason'] ?? 'No reason supplied';
              return Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: const Color(0xFF080E17), borderRadius: BorderRadius.circular(8)),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(entry.key, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
                    Text('Signal: $signal • Score: $score', style: const TextStyle(fontSize: 11, color: Colors.white70)),
                    Text('Reason: $reason', style: const TextStyle(fontSize: 10, color: Colors.white60)),
                    Text('Execution ID: ${trace['execution_id'] ?? details['execution_id'] ?? 'not supplied'}',
                      style: const TextStyle(fontSize: 10, color: Colors.white54)),
                    Text('Version: ${trace['strategy_version'] ?? details['strategy_version'] ?? 'not supplied'} • Input candles: ${trace['input_candle_count'] ?? 'not supplied'}',
                      style: const TextStyle(fontSize: 10, color: Colors.white54)),
                    Text('AI consumed: ${trace['ai_consumed'] ?? 'not proven'} • Research propagated: ${trace['research_engine_received'] ?? 'not proven'}',
                      style: const TextStyle(fontSize: 10, color: Colors.orangeAccent)),
                  ]),
                ),
              );
            }),
            const Text('This panel reads the shared backend signal snapshot. Only fields actually returned by the backend are displayed; missing execution IDs, versions, AI-consumption and propagation evidence are explicitly marked unverified.',
              style: TextStyle(color: Colors.white60, fontSize: 10)),
            Text('Source: ${marketRow['source'] ?? 'not available'} • Quote age: ${marketRow['age_seconds'] ?? 'unknown'} sec', style: const TextStyle(color: Colors.white54, fontSize: 11)),
            if (marketRow['signal_error'] != null || marketRow['error'] != null)
              Text('Signal blocked: ${marketRow['signal_error'] ?? marketRow['error']}', style: const TextStyle(color: Colors.orangeAccent, fontSize: 11)),
          ]),
        )),
        const SizedBox(height: 12),
        TextField(controller: search, onChanged: (_) => setState((){}), decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Search strategies, factors, risk…')),
        const SizedBox(height: 10),
        Wrap(spacing: 6, runSpacing: 6, children: groups.map((g) => ChoiceChip(label: Text(g), selected: category == g, onSelected: (_) => setState(() => category = g))).toList()),
        const SizedBox(height: 12),
        ...filtered.map((x) => Card(color: const Color(0xFF101722), child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [Expanded(child: Text(x['name']!, style: const TextStyle(fontWeight: FontWeight.bold))), Chip(label: Text(x['group']!, style: const TextStyle(fontSize: 10)))]),
          Text(x['detail']!, style: const TextStyle(color: Colors.white70)),
          const SizedBox(height: 6),
          Text('Risk gate: ${x['risk']}', style: const TextStyle(color: Color(0xFF12D6FF), fontSize: 12)),
        ])))),
        const SizedBox(height: 10),
        const Text('Safety: this page is a research catalogue, not proof of profitability. No strategy is marked live or approved here. Use timestamped market data, brokerage costs/slippage, out-of-sample and walk-forward tests, and existing fail-closed risk gates. Deep-learning/RL models must be trained and validated separately; no strategy is approved until measured tests pass.', style: TextStyle(color: Colors.orangeAccent, fontSize: 12)),
      ])),
    );
  }
}
