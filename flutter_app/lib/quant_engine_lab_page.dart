import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart';

/// Integrates the existing live backend capabilities into one research workspace.
/// It never fabricates quotes and never submits broker orders.
class QuantEngineLabPage extends StatefulWidget {
  const QuantEngineLabPage({
    required this.backendUrl,
    required this.index,
    required this.market,
    required this.lastFetch,
    required this.onOpenBacktest,
    super.key,
  });

  final String backendUrl;
  final String index;
  final Map<String, dynamic> market;
  final String? lastFetch;
  final VoidCallback onOpenBacktest;

  @override
  State<QuantEngineLabPage> createState() => _QuantEngineLabPageState();
}

class _QuantEngineLabPageState extends State<QuantEngineLabPage> {
  late FreshApi _api;
  bool _busy = false;
  String? _error;
  Map<String, dynamic> _ticks = const {};
  Map<String, dynamic> _angel = const {};
  Map<String, dynamic> _aiStatus = const {};
  Map<String, dynamic> _paper = const {};
  Map<String, dynamic> _report = const {};
  Map<String, dynamic> _sentiment = const {};
  Map<String, dynamic> _reflection = const {};
  final TextEditingController _headline = TextEditingController();
  final TextEditingController _grossR = TextEditingController(text: '1.0');
  String _side = 'LONG';

  @override
  void initState() {
    super.initState();
    _api = FreshApi(widget.backendUrl);
    // Avoid a hidden network request while a page is being constructed; the
    // user can explicitly refresh live ticks and the paper ledger from the UI.
  }

  @override
  void didUpdateWidget(covariant QuantEngineLabPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.backendUrl != widget.backendUrl) {
      _api = FreshApi(widget.backendUrl);
    }
  }

  @override
  void dispose() {
    _headline.dispose();
    _grossR.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>?> _safeLoad(
    String label,
    Future<Map<String, dynamic>> Function() request,
    List<String> errors,
  ) async {
    try {
      return await request();
    } catch (e) {
      errors.add('$label: $e');
      return null;
    }
  }

  Future<void> _loadResearchData() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final errors = <String>[];
    try {
      // These reads are independent. Run them concurrently so one slow broker
      // diagnostic cannot hold up the paper ledger, AI status, or tick snapshot.
      final results = await Future.wait<Object?>([
        _safeLoad('Angel One status', _api.angelStatus, errors),
        _safeLoad('AI provider status', () => _api.getJson('/v1/ai/status'), errors),
        _safeLoad('Live ticks', _api.marketTicks, errors),
        _safeLoad('Paper ledger', _api.paperTrades, errors),
        _safeLoad('Paper report', _api.paperReport, errors),
      ]);
      if (!mounted) return;
      setState(() {
        // Keep the last known good panel data if only one endpoint failed.
        if (results[0] is Map) _angel = Map<String, dynamic>.from(results[0] as Map);
        if (results[1] is Map) _aiStatus = Map<String, dynamic>.from(results[1] as Map);
        if (results[2] is Map) _ticks = Map<String, dynamic>.from(results[2] as Map);
        if (results[3] is Map) _paper = Map<String, dynamic>.from(results[3] as Map);
        if (results[4] is Map) _report = Map<String, dynamic>.from(results[4] as Map);
        _error = errors.isEmpty ? null : errors.join('\n');
        _busy = false;
      });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _busy = false; });
    }
  }

  Future<void> _startLiveStream() async {
    setState(() { _busy = true; _error = null; });
    try {
      _angel = await _api.angelStatus();
      if (_angel['authenticated'] != true) {
        final reason = _angel['last_error'] ?? _angel['feed_error'] ?? 'No authenticated session';
        throw Exception('Angel One is NOT authenticated. Open API / Trading Setup, log in with current TOTP, then retry. Details: $reason');
      }
      await _api.startStream([widget.index]);
      _angel = await _api.angelStatus();
      _ticks = await _api.marketTicks();
      if (mounted) {
        setState(() => _busy = false);
        _snack('Stream accepted. Authenticated=${_angel['authenticated']}; WebSocket=${_angel['stream_open']}; last tick age=${_angel['last_tick_age_seconds'] ?? 'unknown'} sec. Verify fresh ticks before trusting signals.');
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _busy = false; });
    }
  }

  Future<void> _syncInstruments() async {
    setState(() { _busy = true; _error = null; });
    try {
      final result = await _api.syncInstruments();
      if (mounted) {
        setState(() => _busy = false);
        _snack('Instrument sync: ${result['count'] ?? result['rows'] ?? result['status'] ?? 'completed'}. Inspect the API response if no count is returned.');
      }
      await _loadResearchData();
    } catch (e) {
      if (mounted) setState(() { _error = 'Instrument sync failed: $e'; _busy = false; });
    }
  }

  Future<void> _analyzeHeadline() async {
    final headline = _headline.text.trim();
    if (headline.isEmpty) {
      _snack('Paste a headline or news excerpt first.');
      return;
    }
    setState(() { _busy = true; _error = null; _sentiment = const {}; });
    try {
      final result = await _api.aiChat(
        index: widget.index,
        question: 'Analyze this user-supplied news text for trading research. '
            'Return: sentiment (positive/negative/neutral/mixed), confidence with caveat, '
            'key evidence quoted only from the supplied text, possible market relevance, '
            'and what cannot be verified. Do not claim this is verified current news, '
            'do not invent facts or prices, and do not give a guaranteed trade instruction.\n\n'
            'USER-SUPPLIED TEXT:\n$headline',
      );
      if (mounted) setState(() { _sentiment = result; _busy = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _busy = false; });
    }
  }

  Future<void> _reflectOnPaperResults() async {
    final closed = _trades.where((t) => t is Map && t['status'] == 'CLOSED').toList();
    if (closed.isEmpty) {
      _snack('Close at least one paper trade before requesting a reflection.');
      return;
    }
    setState(() { _busy = true; _error = null; _reflection = const {}; });
    try {
      final compactTrades = closed.take(30).map((item) {
        final t = Map<String, dynamic>.from(item as Map);
        return {
          'index': t['index'],
          'side': t['side'],
          'regime': t['regime'],
          'gross_r': t['gross_r'],
          'net_r': t['net_r'],
          'slippage_r': t['slippage_r'],
          'transaction_cost_r': t['transaction_cost_r'],
          'notes': t['notes'],
        };
      }).toList();
      final result = await _api.aiChat(
        index: widget.index,
        question: 'Review these CLOSED PAPER-ONLY trade outcomes. Identify repeated patterns, '
            'whether costs changed results, limitations of the small sample, and specific '
            'questions for further validation. Do not infer unprovided prices or market causes, '
            'do not claim statistical significance from a small sample, and do not recommend '
            'automatic live execution. Paper report: ${jsonEncode(_report)}. Trades: ${jsonEncode(compactTrades)}',
      );
      if (mounted) setState(() { _reflection = result; _busy = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _busy = false; });
    }
  }

  Future<void> _openPaperTrade() async {
    setState(() { _busy = true; _error = null; });
    try {
      final id = 'paper-${DateTime.now().millisecondsSinceEpoch}';
      await _api.openPaperTrade(
        tradeId: id,
        strategyId: 'quant-engine-lab',
        index: widget.index,
        side: _side,
        regime: 'UNVERIFIED',
        slippageR: 0.02,
        transactionCostR: 0.02,
        notes: 'Paper-only research entry; no broker order submitted.',
      );
      await _loadResearchData();
      if (mounted) _snack('Paper trade opened: $id');
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _busy = false; });
    }
  }

  Future<void> _closePaperTrade(String tradeId) async {
    final grossR = double.tryParse(_grossR.text.trim());
    if (grossR == null) {
      _snack('Enter a valid gross result in R units.');
      return;
    }
    setState(() { _busy = true; _error = null; });
    try {
      await _api.closePaperTrade(
        tradeId: tradeId,
        grossR: grossR,
        notes: 'User-entered paper result; validate against actual fills before using for research.',
      );
      await _loadResearchData();
      if (mounted) _snack('Paper trade closed. Net R deducts saved slippage and costs.');
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _busy = false; });
    }
  }

  void _snack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Map<String, dynamic> get _stream =>
      Map<String, dynamic>.from(_ticks['stream'] as Map? ?? const {});
  bool get _angelAuthenticated => _angel['authenticated'] == true;
  bool get _streamOpen => _angel['stream_open'] == true || _stream['stream_open'] == true;
  String get _angelLabel => !_angelAuthenticated
      ? 'NOT CONNECTED'
      : (_streamOpen ? 'AUTHENTICATED • WS OPEN' : 'AUTHENTICATED • WS NOT OPEN');
  List<dynamic> get _tickRows => (_ticks['ticks'] as List?) ?? const [];
  List<dynamic> get _trades => (_paper['trades'] as List?) ?? const [];
  List<dynamic> get _openTrades =>
      _trades.where((t) => t is Map && t['status'] == 'OPEN').toList();

  @override
  Widget build(BuildContext context) {
    final indexRow = Map<String, dynamic>.from(widget.market[widget.index] as Map? ?? const {});
    final live = indexRow['live'] == true;
    final ltp = indexRow['ltp'];
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const Text('QUANT ENGINE LAB', style: TextStyle(fontSize: 19, fontWeight: FontWeight.w900, letterSpacing: 1)),
        const SizedBox(height: 5),
        Text('Live data, paper-trade learning, news reasoning and execution review • ${widget.index}',
            style: const TextStyle(color: Colors.white70)),
        const SizedBox(height: 10),
        if (_error != null)
          Card(
            color: Colors.red.withValues(alpha: 0.10),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_error!, style: const TextStyle(color: Colors.orangeAccent)),
            ),
          ),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const _LabHeading(icon: Icons.sensors, title: '1. Streaming vs offline research'),
              const SizedBox(height: 7),
              Text('Angel One: ${_angelLabel}'),
              Text('Stored session: ${_angel['stored_session'] ?? 'unknown'} • JWT: ${_angel['stored_jwt'] ?? 'unknown'} • Feed token: ${_angel['stored_feed_token'] ?? 'unknown'}'),
              if ((_angel['last_error'] ?? _angel['feed_error']) != null)
                Text('Angel error: ${_angel['last_error'] ?? _angel['feed_error']}', style: const TextStyle(color: Colors.orangeAccent)),
              Text('Index snapshot: ${ltp ?? 'No price'} • ${live ? 'LIVE' : (indexRow['age_seconds'] != null ? 'STALE / LAST FETCH' : 'NO SNAPSHOT')}'),
              Text('Snapshot source: ${indexRow['source'] ?? 'unknown'} • timestamp: ${indexRow['timestamp'] ?? widget.lastFetch ?? 'not recorded'}'),
              Text('Snapshot age: ${indexRow['age_seconds'] ?? 'unknown'} sec • mode: ${indexRow['feed_mode'] ?? 'HISTORICAL / UNKNOWN'}'),
              Text('WebSocket open: ${_streamOpen} • last tick age: ${_angel['last_tick_age_seconds'] ?? 'unknown'} sec • ticks in store: ${_ticks['count'] ?? 0}'),
              Text('AI provider: ${_aiStatus['provider'] ?? 'unknown'} • model: ${_aiStatus['model'] ?? 'unknown'} • status: ${_aiStatus['status'] ?? 'not checked'}'),
              const SizedBox(height: 9),
              Wrap(spacing: 8, runSpacing: 8, children: [
                FilledButton.icon(
                  onPressed: _busy ? null : _startLiveStream,
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Start live stream'),
                ),
                OutlinedButton.icon(
                  onPressed: _busy ? null : _syncInstruments,
                  icon: const Icon(Icons.sync),
                  label: const Text('Sync instruments'),
                ),
                OutlinedButton.icon(
                  onPressed: _busy ? null : _loadResearchData,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh status/data'),
                ),
              ]),
              const SizedBox(height: 5),
              const Text('Historical experiments should use saved/historical candles; live snapshots are not substituted for offline training data.',
                  style: TextStyle(fontSize: 11, color: Colors.white60)),
            ]),
          ),
        ),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const _LabHeading(icon: Icons.psychology_alt, title: '2. AI news sentiment + reasoning'),
              const SizedBox(height: 7),
              const Text('Paste a headline or excerpt. The configured server-side AI will analyze only the supplied text and available market context; it does not verify news freshness.'),
              const SizedBox(height: 9),
              TextField(
                controller: _headline,
                minLines: 2,
                maxLines: 5,
                decoration: const InputDecoration(
                  labelText: 'News headline / excerpt',
                  hintText: 'Paste text to analyze…',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: _busy ? null : _analyzeHeadline,
                icon: const Icon(Icons.analytics_outlined),
                label: const Text('Analyze sentiment with AI'),
              ),
              if (_sentiment.isNotEmpty) ...[
                const Divider(height: 20),
                Text('Model: ${_sentiment['model'] ?? 'unknown'} • Context available: ${_sentiment['market_context_available'] ?? 'unknown'}',
                    style: const TextStyle(color: Colors.white60, fontSize: 11)),
                const SizedBox(height: 6),
                SelectableText((_sentiment['answer'] ?? jsonEncode(_sentiment)).toString()),
              ],
            ]),
          ),
        ),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const _LabHeading(icon: Icons.school, title: '3. Paper trading + outcome memory'),
              const SizedBox(height: 7),
              Text('Mode: ${_paper['mode'] ?? 'not connected'} • Open: ${_report['open_trades'] ?? _openTrades.length} • Closed: ${_report['closed_trades'] ?? 0}'),
              Text('Risk gate: ${((_report['risk'] as Map?)?['blocked']) == true ? 'BLOCKED' : 'not blocked / not verified'}'),
              const SizedBox(height: 8),
              Row(children: [
                const Text('Side'),
                const SizedBox(width: 10),
                DropdownButton<String>(
                  value: _side,
                  items: const [
                    DropdownMenuItem(value: 'LONG', child: Text('LONG')),
                    DropdownMenuItem(value: 'SHORT', child: Text('SHORT')),
                  ],
                  onChanged: _busy ? null : (value) => setState(() => _side = value ?? 'LONG'),
                ),
                const Spacer(),
                FilledButton(
                  onPressed: _busy ? null : _openPaperTrade,
                  child: const Text('Open paper trade'),
                ),
              ]),
              if (_openTrades.isEmpty)
                const Text('No open paper trades.', style: TextStyle(color: Colors.white60))
              else ...[
                const SizedBox(height: 5),
                const Text('Close a paper trade after entering its gross result in R units. This never places a live order.'),
                TextField(
                  controller: _grossR,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                  decoration: const InputDecoration(labelText: 'Gross result (R) for closing'),
                ),
                for (final trade in _openTrades)
                  if (trade is Map)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text('${trade['trade_id'] ?? 'Unknown trade'}'),
                      subtitle: Text('${trade['index'] ?? ''} • ${trade['side'] ?? ''} • costs ${trade['slippage_r'] ?? 0}R + ${trade['transaction_cost_r'] ?? 0}R'),
                      trailing: TextButton(
                        onPressed: _busy ? null : () => _closePaperTrade((trade['trade_id'] ?? '').toString()),
                        child: const Text('Close'),
                      ),
                    ),
              ],
              const SizedBox(height: 6),
              OutlinedButton.icon(
                onPressed: _busy ? null : _reflectOnPaperResults,
                icon: const Icon(Icons.psychology),
                label: const Text('Reflect on closed paper trades with AI'),
              ),
              if (_reflection.isNotEmpty) ...[
                const SizedBox(height: 8),
                SelectableText((_reflection['answer'] ?? jsonEncode(_reflection)).toString()),
              ],
              const SizedBox(height: 6),
              Text('Ledger storage: ${_report['persistence'] ?? 'unknown'} • Net performance subtracts costs from the entered gross R.',
                  style: const TextStyle(fontSize: 11, color: Colors.white60)),
            ]),
          ),
        ),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const _LabHeading(icon: Icons.query_stats, title: '4. Strategy validation + historical replay'),
              const SizedBox(height: 7),
              const Text('Replay Angel One historical index candles with EMA/ATR rules. Check sample size, slippage, costs and out-of-sample performance before trusting results.'),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: widget.onOpenBacktest,
                icon: const Icon(Icons.replay),
                label: const Text('Open historical backtesting'),
              ),
              const SizedBox(height: 8),
              const Text('This lab does not train a model on live ticks or claim a backtest result unless the backend returns actual historical data.',
                  style: TextStyle(color: Colors.white60, fontSize: 11)),
            ]),
          ),
        ),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const _LabHeading(icon: Icons.speed, title: '5. Tick / order-book execution review'),
              const SizedBox(height: 7),
              Text('Observed tick records: ${_tickRows.length} • stream: ${_stream['status'] ?? _stream['connected'] ?? 'unknown'}'),
              if (_tickRows.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text('No tick records returned. Start the stream and verify Angel One session before reviewing execution. No synthetic ticks are generated.',
                      style: TextStyle(color: Colors.orangeAccent)),
                )
              else
                for (final item in _tickRows.take(12))
                  if (item is Map)
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.show_chart, size: 18),
                      title: Text('${item['symbol'] ?? item['tradingsymbol'] ?? item['token'] ?? 'Instrument'} • LTP ${item['ltp'] ?? item['last_traded_price'] ?? 'unknown'}'),
                      subtitle: Text('Bid ${item['bid'] ?? item['best_bid'] ?? 'not supplied'} • Ask ${item['ask'] ?? item['best_ask'] ?? 'not supplied'} • Time ${item['timestamp'] ?? item['exchange_timestamp'] ?? 'unknown'}'),
                    ),
              const Text('HftBacktest-style tick-by-tick replay needs historical tick + depth/order-book data. This screen reports only fields actually returned by the broker; it will not invent missing depth or execution fills.',
                  style: TextStyle(fontSize: 11, color: Colors.white60)),
            ]),
          ),
        ),
        if (_busy) const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())),
        const SizedBox(height: 12),
      ],
    );
  }
}

class _LabHeading extends StatelessWidget {
  const _LabHeading({required this.icon, required this.title});
  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(icon, color: const Color(0xFF12D6FF), size: 21),
      const SizedBox(width: 8),
      Expanded(child: Text(title, style: const TextStyle(fontWeight: FontWeight.w800))),
    ],
  );
}
