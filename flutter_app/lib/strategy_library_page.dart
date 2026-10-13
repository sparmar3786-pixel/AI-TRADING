import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class StrategyLibraryPage extends StatefulWidget {
  const StrategyLibraryPage({required this.market, required this.signals, required this.selectedIndex, super.key});
  final Map<String, dynamic> market;
  final Map<String, dynamic> signals;
  final String selectedIndex;
  @override
  State<StrategyLibraryPage> createState() => _StrategyLibraryPageState();
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
  static const sources = <Map<String,String>>[
    {'title':'Awesome Systematic Trading','url':'https://github.com/paperswithbacktest/awesome-systematic-trading','desc':'Strategies, backtesting tools, research papers, data and execution libraries.'},
    {'title':'Awesome Quant','url':'https://github.com/wilsonfreitas/awesome-quant','desc':'Quant libraries for indicators, portfolio/risk, time series, market data and backtesting.'},
    {'title':'Awesome Deep Trading','url':'https://github.com/cbailes/awesome-deep-trading','desc':'Deep-learning trading papers, reinforcement learning, datasets and code.'},
    {'title':'Backtest-Kit: First Backtest','url':'https://backtest-kit.github.io/documents/example_02_first_backtest.html','desc':'Example walkthrough for constructing and running a backtest.'},
  ];
  @override
  void dispose() { search.dispose(); super.dispose(); }
  Future<void> open(String value) async {
    final uri = Uri.tryParse(value);
    if (uri == null || !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open link. Check internet connection.')));
    }
  }
  @override
  Widget build(BuildContext context) {
    final filtered = items.where((x) => (category == 'All' || x['group'] == category) && ('${x['name']} ${x['detail']} ${x['group']}'.toLowerCase().contains(search.text.toLowerCase()))).toList();
    final groups = ['All', ...items.map((x) => x['group']!).toSet()];
    final marketRow = Map<String, dynamic>.from(widget.market[widget.selectedIndex] as Map? ?? const {});
    final signalRow = Map<String, dynamic>.from(widget.signals[widget.selectedIndex] as Map? ?? const {});
    final layers = Map<String, dynamic>.from(signalRow['layers'] as Map? ?? const {});
    final passedLayers = layers.values.whereType<Map>().where((layer) => layer['pass'] == true).length;
    final fresh = marketRow['live'] == true;
    final ltp = marketRow['ltp'];
    return Scaffold(
      backgroundColor: const Color(0xFF070B12),
      body: SafeArea(child: ListView(padding: const EdgeInsets.all(14), children: [
        const Text('STRATEGY & QUANT LIBRARY', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, letterSpacing: 1)),
        const SizedBox(height: 6),
        const Text('Research catalogue • strategies require data validation and backtesting before use.', style: TextStyle(color: Colors.white70)),
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
        const Text('UPSTREAM RESEARCH SOURCES', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
        const SizedBox(height: 6),
        ...sources.map((x) => Card(color: const Color(0xFF101722), child: ListTile(
          leading: const Icon(Icons.open_in_new, color: Color(0xFF12D6FF)),
          title: Text(x['title']!, style: const TextStyle(fontWeight: FontWeight.bold)),
          subtitle: Text(x['desc']!),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => open(x['url']!),
        ))),
        const SizedBox(height: 10),
        const Text('Safety: this page is a research catalogue, not proof of profitability. No strategy is marked live or approved here. Use timestamped market data, brokerage costs/slippage, out-of-sample and walk-forward tests, and existing fail-closed risk gates. Deep-learning/RL models must be trained and validated separately; a link is not an installed model.', style: TextStyle(color: Colors.orangeAccent, fontSize: 12)),
      ])),
    );
  }
}
