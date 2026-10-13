import 'package:flutter/material.dart';
import 'api.dart';

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
  bool _runningSuite = false;
  Map<String, dynamic> _suiteRun = const {};
  String? _suiteRunError;

  Future<void> _runSuite(Map<String, dynamic> marketRow) async {
    final timeframes = Map<String, dynamic>.from(marketRow['timeframes'] as Map? ?? const {});
    List? raw;
    for (final key in ['15m', '15min', '5m', '5min', '1m', '1min']) {
      if (timeframes[key] is List) { raw = timeframes[key] as List; break; }
    }
    raw ??= marketRow['candles'] is List ? marketRow['candles'] as List : null;
    final candles = (raw ?? const []).whereType<Map>().map((row) => Map<String, dynamic>.from(row)).where((row) => row['high'] is num && row['low'] is num && row['close'] is num).toList();
    if (candles.isEmpty) {
      setState(() { _suiteRunError = 'No usable real OHLC candles in the current market snapshot. The strategy suite was not executed.'; _suiteRun = const {}; });
      return;
    }
    setState(() { _runningSuite = true; _suiteRunError = null; _suiteRun = const {}; });
    try {
      final result = await FreshApi().postJson('/v1/strategies/evaluate', {'candles': candles, 'min_consensus': 3}, timeout: const Duration(seconds: 20));
      if (mounted) setState(() { _suiteRun = result; });
    } catch (error) {
      if (mounted) setState(() { _suiteRunError = error.toString(); });
    } finally {
      if (mounted) setState(() { _runningSuite = false; });
    }
  }
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
            if (suite['trace'] is Map) ...[
              Text('Backend execution ID: ${(suite['trace'] as Map)['execution_id'] ?? suite['execution_id'] ?? 'not supplied'}',
                style: const TextStyle(fontSize: 10, color: Colors.white70)),
              Text('Version: ${(suite['trace'] as Map)['strategy_version'] ?? 'not supplied'} • Input candles: ${(suite['trace'] as Map)['input_candle_count'] ?? 'unknown'}',
                style: const TextStyle(fontSize: 10, color: Colors.white54)),
              Text('Input SHA-256: ${(suite['trace'] as Map)['input_sha256'] ?? 'unknown'}',
                style: const TextStyle(fontSize: 9, color: Colors.white38)),
              Text('AI context sent: ${(suite['trace'] as Map)['ai_context_sent'] ?? false} • Research Engine received: ${(suite['trace'] as Map)['research_engine_received'] ?? false} • Trading Setup received: ${(suite['trace'] as Map)['trading_setup_received'] ?? false}',
                style: const TextStyle(fontSize: 10, color: Colors.orangeAccent)),
            ],
            if (suiteStrategies.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text('EXECUTION TRACE UNAVAILABLE • backend returned no per-strategy outputs. Catalogue entries below are not execution evidence.',
                  style: TextStyle(color: Colors.orangeAccent, fontSize: 11, fontWeight: FontWeight.w700)),
              )
            else if (suite['strategy_trace'] is List)
              ...(suite['strategy_trace'] as List).whereType<Map>().map((rawTrace) {
                final item = Map<String, dynamic>.from(rawTrace);
                return Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(color: const Color(0xFF080E17), borderRadius: BorderRadius.circular(8)),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${item['strategy_name'] ?? 'Strategy'} • ${item['signal'] ?? 'WAIT'}',
                        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
                      Text('Reason: ${item['rejection_reason'] ?? 'Directional output returned'}',
                        style: const TextStyle(fontSize: 10, color: Colors.white70)),
                      Text('Execution ID: ${item['strategy_id'] ?? 'not supplied'}',
                        style: const TextStyle(fontSize: 9, color: Colors.white54)),
                      Text('Input bars: ${item['input_candle_count'] ?? 'unknown'} • Score: ${item['score'] ?? 'not computed'}',
                        style: const TextStyle(fontSize: 9, color: Colors.white54)),
                    ]),
                  ),
                );
              })
            else ...suiteStrategies.entries.map((entry) {
              final value = entry.value;
              final details = value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{'signal': value};
              final trace = details['trace'] is Map ? Map<String, dynamic>.from(details['trace'] as Map) : <String, dynamic>{};
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
                  ]),
                ),
              );
            }),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _runningSuite ? null : () => _runSuite(marketRow),
                icon: _runningSuite
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.play_arrow),
                label: Text(_runningSuite ? 'RUNNING LOCAL STRATEGY SUITE…' : 'RUN STRATEGY SUITE ON CURRENT CANDLES'),
              ),
            ),
            if (_suiteRunError != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_suiteRunError!, style: const TextStyle(color: Colors.orangeAccent, fontSize: 11)),
              ),
            if (_suiteRun.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('RUN RESULT: ${_suiteRun['signal'] ?? 'WAIT'} • status ${_suiteRun['status'] ?? 'unknown'} • votes ${(_suiteRun['votes'] as Map?)?.toString() ?? 'not returned'}',
                style: const TextStyle(color: Color(0xFF12D6FF), fontWeight: FontWeight.w900, fontSize: 12)),
              Text('Execution ID: ${_suiteRun['execution_id'] ?? 'missing'}',
                style: const TextStyle(fontSize: 10, color: Colors.white70)),
              Text('Input candles: ${(_suiteRun['trace'] as Map?)?['input_candle_count'] ?? 'unknown'} • SHA-256: ${((_suiteRun['trace'] as Map?)?['input_sha256'] ?? 'unknown').toString()}',
                style: const TextStyle(fontSize: 10, color: Colors.white54)),
              Text('AI consumed: ${(_suiteRun['trace'] as Map?)?['ai_consumed'] ?? 'not proven'} • Research received: ${(_suiteRun['trace'] as Map?)?['research_engine_received'] ?? 'not proven'} • Trading Setup received: ${(_suiteRun['trace'] as Map?)?['trading_setup_received'] ?? 'not proven'}',
                style: const TextStyle(fontSize: 10, color: Colors.orangeAccent)),
              if (_suiteRun['strategies'] is Map)
                ...(_suiteRun['strategies'] as Map).entries.map((entry) => Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Text('${entry.key}: ${entry.value}', style: const TextStyle(fontSize: 11, color: Colors.white70)),
                )),
              if (_suiteRun['strategy_trace'] is List) ...[
                const SizedBox(height: 8),
                const Text('PER-STRATEGY EXECUTION TRACE', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w900, color: Color(0xFF12D6FF))),
                ...(_suiteRun['strategy_trace'] as List).whereType<Map>().map((rawTrace) {
                  final item = Map<String, dynamic>.from(rawTrace);
                  final signal = item['signal'] ?? 'WAIT';
                  final rejection = item['rejection_reason'] ?? 'Directional output returned';
                  return Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(top: 5),
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(color: const Color(0xFF080E17), borderRadius: BorderRadius.circular(8)),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${item['strategy_name'] ?? 'Strategy'} • $signal', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
                      Text('Reason: $rejection', style: const TextStyle(fontSize: 10, color: Colors.white70)),
                      Text('ID: ${item['strategy_id'] ?? 'missing'}', style: const TextStyle(fontSize: 9, color: Colors.white54)),
                      Text('Score: ${item['score'] ?? 'not computed'} • Input bars: ${item['input_candle_count'] ?? 'unknown'}', style: const TextStyle(fontSize: 9, color: Colors.white54)),
                      Text('AI consumed: ${item['ai_consumed'] ?? false} • Research received: ${item['research_engine_received'] ?? false} • Trading Setup received: ${item['trading_setup_received'] ?? false}', style: const TextStyle(fontSize: 9, color: Colors.orangeAccent)),
                    ]),
                  );
                }),
              ],
            ],
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
