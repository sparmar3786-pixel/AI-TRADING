import 'package:flutter/material.dart';
import 'api.dart';

/// Groww-inspired information hierarchy for Fresh-Apk. This intentionally keeps
/// Fresh's existing dark theme and navigation, and does not copy Groww branding.
class TradeEnginePage extends StatefulWidget {
  const TradeEnginePage({
    required this.backendUrl,
    required this.selectedIndex,
    required this.market,
    required this.signals,
    required this.ai,
    required this.tradePlans,
    required this.feed,
    required this.liveStatus,
    required this.lastFetch,
    required this.onIndexChanged,
    super.key,
  });

  final String backendUrl;
  final String selectedIndex;
  final Map<String, dynamic> market;
  final Map<String, dynamic> signals;
  final Map<String, dynamic> ai;
  final List<dynamic> tradePlans;
  final Map<String, dynamic> feed;
  final Map<String, dynamic> liveStatus;
  final String? lastFetch;
  final ValueChanged<String> onIndexChanged;

  @override
  State<TradeEnginePage> createState() => _TradeEnginePageState();
}

class _TradeEnginePageState extends State<TradeEnginePage> {
  String get backendUrl => widget.backendUrl;
  String get selectedIndex => widget.selectedIndex;
  Map<String, dynamic> get market => widget.market;
  Map<String, dynamic> get signals => widget.signals;
  Map<String, dynamic> get ai => widget.ai;
  List<dynamic> get tradePlans => widget.tradePlans;
  Map<String, dynamic> get feed => widget.feed;
  Map<String, dynamic> get liveStatus => widget.liveStatus;
  String? get lastFetch => widget.lastFetch;
  ValueChanged<String> get onIndexChanged => widget.onIndexChanged;

  Future<Map<String, dynamic>>? _ordersFuture;
  Future<Map<String, dynamic>> _loadOrders() => FreshApi(backendUrl).getJson('/v1/live/orders');

  static const _cyan = Color(0xFF12D6FF);

  Map<String, dynamic> _map(dynamic value) =>
      Map<String, dynamic>.from(value as Map? ?? const {});

  String _value(dynamic value) {
    if (value == null || value.toString().isEmpty) return '—';
    if (value is num) return value.toStringAsFixed(value.abs() >= 100 ? 2 : 3);
    return value.toString();
  }

  @override
  Widget build(BuildContext context) {
    final m = _map(market[selectedIndex]);
    final s = _map(signals[selectedIndex]);
    final a = _map(ai[selectedIndex]);
    final validation = _map(s['live_validation']);
    final checks = _map(validation['checks']);
    final quant = _map(s['quant_engine'] ?? s['five_layer_engine']);
    final quantLayers = _map(quant['layers']);
    final orderFlow = _map(quantLayers['order_flow'] ?? s['order_flow']);
    final trendLayer = _map(quantLayers['trend_sentiment'] ?? s['trend_sentiment']);
    final optionLayer = _map(quantLayers['option_selection'] ?? s['option_validation']);
    final riskLayer = _map(quantLayers['risk_levels'] ?? s['risk_validation']);
    final stability = _map(s['signal_stability'] ?? quantLayers['confirmation']);
    final blocks = (validation['blocks'] as List?) ?? const <dynamic>[];
    final plan = _map(s['trade_plan']);
    final decision = (s['decision'] ?? 'NO DATA').toString();
    final verdict = (validation['verdict'] ?? 'NOT VALIDATED').toString();
    final isFresh = m['live'] == true;
    final layerTwoPass = verdict == 'PASS';
    final candidate = decision == 'CALL BUY' || decision == 'PUT BUY';
    final mode = (liveStatus['mode'] ?? 'CHECK STATUS').toString();

    return ListView(
      key: const ValueKey('trade-engine-primary-list'),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                'TRADE ENGINE',
                style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1.2),
              ),
            ),
            _pill(isFresh ? 'LIVE DATA' : 'DATA CHECK', isFresh ? Colors.greenAccent : Colors.orangeAccent),
          ],
        ),
        const SizedBox(height: 10),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Market overview', style: TextStyle(color: Colors.white70)),
                const SizedBox(height: 5),
                DropdownButtonFormField<String>(
                  initialValue: selectedIndex,
                  decoration: const InputDecoration(labelText: 'F&O index'),
                  items: const ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX']
                      .map((name) => DropdownMenuItem(value: name, child: Text(name)))
                      .toList(),
                  onChanged: (value) {
                    if (value != null) onIndexChanged(value);
                  },
                ),
                const SizedBox(height: 12),
                Text(selectedIndex, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900)),
                Text('₹ ${_value(m['ltp'])}', style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: _cyan)),
                const SizedBox(height: 6),
                Text('Feed: ${m['feed_mode'] ?? m['source'] ?? 'NO DATA'}'),
                Text('Quote age: ${m['age_seconds'] == null ? '—' : '${m['age_seconds']} sec'}'),
                Text('Last fetched: ${m['timestamp'] ?? lastFetch ?? 'No market snapshot'}', style: const TextStyle(fontSize: 11, color: Colors.white60)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 4),
        _layerHeader('01', 'SIGNAL ENGINE', 'Candidate generation • Layer 1', candidate ? 'CANDIDATE' : 'WAIT / NO TRADE', candidate ? Colors.lightBlueAccent : Colors.orangeAccent),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(decision, style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: decision == 'CALL BUY' ? Colors.greenAccent : decision == 'PUT BUY' ? Colors.redAccent : Colors.orangeAccent)),
                const SizedBox(height: 6),
                Text((s['reason'] as List?)?.map((x) => x.toString()).join(' • ') ?? 'No strategy explanation returned yet.'),
                const Divider(height: 20),
                _metricGrid([
                  ('Confidence', '${s['confidence'] ?? '—'}%'),
                  ('Strike', _value(s['strike'])),
                  ('Option', (s['option_side'] ?? '—').toString()),
                  ('Entry', _value(s['entry'])),
                  ('Stop loss', _value(s['stop_loss'])),
                  ('Target 1', _value(s['target'] ?? plan['target1'])),
                  ('Target 2', _value(plan['target2'])),
                  ('Target 3', _value(plan['target3'])),
                ]),
                const SizedBox(height: 8),
                Text('AI review: ${a['action'] ?? a['decision'] ?? 'WAITING / NOT CONFIGURED'}'),
                Text('AI rationale: ${(a['why'] as List?)?.map((x) => x.toString()).join(' • ') ?? 'No AI explanation available.'}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        _layerHeader('02', 'RISK & VALIDATION', 'Independent deterministic gate • Layer 2', verdict, layerTwoPass ? Colors.greenAccent : Colors.orangeAccent),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(layerTwoPass ? 'Validation passed' : 'Signal blocked until checks pass', style: const TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                _metricGrid([
                  ('Final action', (validation['decision'] ?? 'WAIT').toString()),
                  ('Reward / risk', _value(validation['reward_risk'])),
                  ('Market tick age', validation['market_age_seconds'] == null ? '—' : '${validation['market_age_seconds']} sec'),
                  ('Option quote age', validation['option_age_seconds'] == null ? '—' : '${validation['option_age_seconds']} sec'),
                ]),
                const Divider(height: 18),
                if (checks.isEmpty)
                  const Text('Backend has not returned validation checks. This screen will not infer a PASS from an AI recommendation.', style: TextStyle(color: Colors.orangeAccent))
                else
                  ...checks.entries.map((entry) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(
                      children: [
                        Icon(entry.value == true ? Icons.check_circle : Icons.cancel, size: 16, color: entry.value == true ? Colors.greenAccent : Colors.orangeAccent),
                        const SizedBox(width: 8),
                        Expanded(child: Text(entry.key.replaceAll('_', ' '), style: const TextStyle(fontSize: 12))),
                        Text(entry.value == true ? 'PASS' : 'BLOCK', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: entry.value == true ? Colors.greenAccent : Colors.orangeAccent)),
                      ],
                    ),
                  )),
                if (blocks.isNotEmpty) ...[
                  const Divider(height: 18),
                  const Text('Blocking reasons', style: TextStyle(fontWeight: FontWeight.w800, color: Colors.orangeAccent)),
                  ...blocks.map((reason) => Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text('• ${reason.toString().replaceAll('_', ' ')}', style: const TextStyle(fontSize: 12)),
                  )),
                ],
                const SizedBox(height: 8),
                const Text('Fail-closed rule: stale/missing data, invalid quote, conflicting AI, bad SL/target, or failed risk checks means WAIT. AI confidence is not a profit probability.', style: TextStyle(fontSize: 11, color: Colors.white70)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        _layerHeader('03', 'TREND & SENTIMENT', 'Multi-timeframe trend + session sentiment • Layer 3', (trendLayer['pass'] == true) ? 'PASS' : 'DATA REQUIRED', (trendLayer['pass'] == true) ? Colors.greenAccent : Colors.orangeAccent),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _row('Trend', (trendLayer['trend'] ?? m['trend'] ?? 'NOT PROVIDED BY BACKEND').toString()),
                _row('Session sentiment', (trendLayer['sentiment_direction'] ?? m['sentiment_direction'] ?? 'NOT PROVIDED').toString()),
                _row('Sentiment score', _value(trendLayer['sentiment_score'] ?? m['sentiment_score'])),
                _row('Timeframe agreement', trendLayer['timeframes'] is Map ? (trendLayer['timeframes'] as Map).entries.map((e) => '${e.key}: ${e.value}').join(' • ') : 'Multi-timeframe evidence unavailable'),
                const Text('Trend/sentiment must come from fresh market/news evidence; missing data is not treated as neutral confirmation.', style: TextStyle(fontSize: 11, color: Colors.white70)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        _layerHeader('04', 'OPTION CHAIN & ORDER FLOW', 'Strike liquidity, bid/ask spread, OI and flow • Layer 4', (optionLayer['pass'] == true && orderFlow['pass'] == true) ? 'PASS' : 'DATA REQUIRED', (optionLayer['pass'] == true && orderFlow['pass'] == true) ? Colors.greenAccent : Colors.orangeAccent),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _metricGrid([
                  ('Selected strike', _value(optionLayer['strike'] ?? s['strike'])),
                  ('Expiry', (optionLayer['expiry'] ?? s['expiry'] ?? '—').toString()),
                  ('Option spread %', _value(optionLayer['spread_pct'] ?? s['option_spread_pct'])),
                  ('Flow direction', (orderFlow['direction'] ?? s['order_flow_direction'] ?? 'NOT PROVIDED').toString()),
                  ('Flow imbalance', _value(orderFlow['imbalance'] ?? s['order_flow_imbalance'])),
                  ('OI context', (s['oi_context'] ?? 'NOT PROVIDED').toString()),
                ]),
                const SizedBox(height: 8),
                const Text('Do not infer bid/ask pressure or OI from a chart image. This layer passes only when the backend supplies valid, fresh contract and flow fields.', style: TextStyle(fontSize: 11, color: Colors.white70)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        _layerHeader('05', 'RISK & 10-MINUTE STABILITY', 'Entry, stop, target and continuous confirmation • Layer 5', (riskLayer['pass'] == true && stability['state'] == 'CONFIRMED') ? 'CONFIRMED' : 'WAIT / CONFIRMING', (riskLayer['pass'] == true && stability['state'] == 'CONFIRMED') ? Colors.greenAccent : Colors.orangeAccent),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _metricGrid([
                  ('Entry reference', _value(riskLayer['entry_reference'] ?? s['entry'])),
                  ('Stop loss', _value(riskLayer['stop_loss'] ?? s['stop_loss'])),
                  ('Target', _value(riskLayer['target'] ?? s['target'])),
                  ('RR method', (riskLayer['method'] ?? validation['risk_method'] ?? 'NOT PROVIDED').toString()),
                  ('Stability', (stability['state'] ?? 'NOT VERIFIED').toString()),
                  ('Seconds remaining', _value(stability['remaining_seconds'])),
                ]),
                const SizedBox(height: 8),
                const Text('The app remains WAIT until fresh evidence, valid risk levels and an uninterrupted 10-minute same-side/same-strike confirmation are all verified. This is not a guarantee of profit or minimum holding duration.', style: TextStyle(fontSize: 11, color: Colors.white70)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        _layerHeader('MONITOR', 'READ-ONLY BROKER MONITOR', 'Order book visibility only; this APK does not place orders', mode, Colors.lightBlueAccent),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              children: [
                _row('Execution mode', mode),
                _row('Live orders enabled', liveStatus['live_execution_enabled'] == true ? 'YES' : 'NO'),
                _row('Orders today', '${liveStatus['orders_today'] ?? 0} / ${liveStatus['max_orders_per_day'] ?? '—'}'),
                _row('Broker session', feed['authenticated'] == true ? 'AUTHENTICATED' : 'NOT CONFIRMED'),
                _row('Qualified plans', tradePlans.length.toString()),
                const SizedBox(height: 8),
                SizedBox(width: double.infinity, child: OutlinedButton.icon(
                  onPressed: () => setState(() => _ordersFuture = _loadOrders()),
                  icon: const Icon(Icons.sync),
                  label: const Text('LOAD / REFRESH ANGEL ONE ORDER BOOK'),
                )),
                if (_ordersFuture != null) _orderBookSection(),
                const SizedBox(height: 8),
                const Text('Order status is read from Angel One only when requested. This tab does not submit orders or invent fills/P&L; a submitted order is not proof of a fill.', style: TextStyle(fontSize: 11, color: Colors.white70)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),

      ],
    );
  }

  Widget _orderBookSection() => FutureBuilder<Map<String, dynamic>>(
    future: _ordersFuture,
    builder: (context, snapshot) {
      if (snapshot.connectionState != ConnectionState.done) {
        return const Padding(
          padding: EdgeInsets.all(12),
          child: Center(child: CircularProgressIndicator()),
        );
      }
      if (snapshot.hasError) {
        return Padding(
          padding: const EdgeInsets.all(8),
          child: Text(
            'Angel One order book unavailable: ${snapshot.error.toString().replaceFirst('Exception: ', '')}',
            style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
          ),
        );
      }
      final data = snapshot.data ?? const <String, dynamic>{};
      final orders = (data['orders'] as List?) ?? const <dynamic>[];
      if (orders.isEmpty) {
        return const ListTile(
          dense: true,
          leading: Icon(Icons.receipt_long_outlined),
          title: Text('No broker orders returned'),
          subtitle: Text('The authenticated Angel One order book returned an empty list.'),
        );
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Divider(),
          Text('BROKER ORDER BOOK • ${orders.length} orders', style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 12)),
          for (final raw in orders.take(10))
            if (raw is Map)
              Card(
                child: ExpansionTile(
                  title: Text((raw['tradingsymbol'] ?? raw['symbol'] ?? raw['tradingSymbol'] ?? 'Order').toString()),
                  subtitle: Text('Status: ${raw['orderstatus'] ?? raw['status'] ?? 'UNKNOWN'} • Qty: ${raw['quantity'] ?? raw['qty'] ?? '—'}'),
                  children: [
                    for (final entry in raw.entries)
                      _row(entry.key.toString(), entry.value?.toString() ?? '—'),
                  ],
                ),
              ),
        ],
      );
    },
  );

  Widget _pill(String label, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.12), border: Border.all(color: color.withValues(alpha: 0.5)), borderRadius: BorderRadius.circular(20)),
    child: Text(label, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w900)),
  );

  Widget _layerHeader(String number, String title, String subtitle, String state, Color color) => Card(
    child: ListTile(
      leading: CircleAvatar(backgroundColor: _cyan.withValues(alpha: 0.14), child: Text(number, style: const TextStyle(color: _cyan, fontWeight: FontWeight.w900))),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 13)),
      subtitle: Text(subtitle, style: const TextStyle(fontSize: 11)),
      trailing: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 105), child: Text(state, textAlign: TextAlign.end, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w900))),
    ),
  );

  Widget _metricGrid(List<(String, String)> values) => LayoutBuilder(
    builder: (context, constraints) {
      final width = (constraints.maxWidth - 10) / 2;
      return Wrap(
        spacing: 10,
        runSpacing: 10,
        children: values.map((item) => SizedBox(
          width: width,
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.035), borderRadius: BorderRadius.circular(10)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(item.$1, style: const TextStyle(fontSize: 11, color: Colors.white60)),
              const SizedBox(height: 4),
              Text(item.$2, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
            ]),
          ),
        )).toList(),
      );
    },
  );

  Widget _row(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Row(children: [Expanded(child: Text(label, style: const TextStyle(color: Colors.white70))), Flexible(child: Text(value, textAlign: TextAlign.end, style: const TextStyle(fontWeight: FontWeight.w800)))]),
  );
}
