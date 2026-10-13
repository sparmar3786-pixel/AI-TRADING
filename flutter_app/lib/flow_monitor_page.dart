import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';
import 'order_flow_page.dart';

/// Cross-tab transport and validation monitor. Values are measured at runtime;
/// missing metrics stay unavailable rather than being guessed.
class FlowMonitorPage extends StatefulWidget {
  const FlowMonitorPage({required this.signalBackendUrl, super.key});
  final String signalBackendUrl;

  @override
  State<FlowMonitorPage> createState() => _FlowMonitorPageState();
}

class _FlowMonitorPageState extends State<FlowMonitorPage> {
  late final FreshApi api = FreshApi(null, null, widget.signalBackendUrl);
  Timer? timer;
  bool loading = false, testing = false;
  Map<String, dynamic> diagnostics = const {};
  Map<String, dynamic> signalsPayload = const {};
  Map<String, dynamic> providerResult = const {};
  String? error;
  final List<String> notifications = <String>[];
  String? lastRouteErrorSignature;
  String? lastEngineSignature;

  String fmt(dynamic value, [String unit = '']) {
    if (value == null) return 'Not measured';
    if (value is num) return '${value.toStringAsFixed(value.abs() >= 100 ? 1 : 2)}$unit';
    return '$value$unit';
  }

  @override
  void initState() {
    super.initState();
    refresh();
    timer = Timer.periodic(const Duration(seconds: 10), (_) => refresh());
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  Future<void> refresh() async {
    if (loading) return;
    loading = true;
    try {
      final responses = await Future.wait<Map<String, dynamic>>([
        api.systemDiagnostics().timeout(const Duration(seconds: 12)),
        api.signals().timeout(const Duration(seconds: 12)),
      ]);
      final next = responses[0];
      final nextSignals = responses[1];
      if (!mounted) return;
      final routes = Map<String, dynamic>.from(next['api_performance'] as Map? ?? const {});
      final bad = routes.entries.where((e) => e.value is Map && ((e.value as Map)['last_status'] is num && ((e.value as Map)['last_status'] as num) >= 400)).map((e) => '${e.key} ${(e.value as Map)['last_status']} errors=${(e.value as Map)['errors'] ?? 0}').join(', ');
      final signalRows = Map<String, dynamic>.from(nextSignals['signals'] as Map? ?? const {});
      final engineSignature = signalRows.entries.map((e) {
        final row = Map<String, dynamic>.from(e.value as Map? ?? const {});
        final perf = Map<String, dynamic>.from(row['performance'] as Map? ?? const {});
        final layers = Map<String, dynamic>.from(row['five_layer_engine'] as Map? ?? row['quant_engine'] as Map? ?? const {});
        final layerRows = Map<String, dynamic>.from(layers['layers'] as Map? ?? const {});
        final passed = layerRows.values.whereType<Map>().where((x) => x['pass'] == true).length;
        return '${e.key}:${row['decision'] ?? 'WAIT'}:$passed/${layerRows.length}:${perf['index_snapshot_ms'] ?? '-'}:${perf['five_layer_validation_ms'] ?? '-'}';
      }).join('|');
      setState(() {
        diagnostics = next;
        signalsPayload = nextSignals;
        error = null;
        if (bad.isNotEmpty && bad != lastRouteErrorSignature) {
          notifications.insert(0, '${DateTime.now().toLocal()} • API error • $bad');
        }
        if (lastEngineSignature != null && engineSignature != lastEngineSignature) {
          notifications.insert(0, '${DateTime.now().toLocal()} • Engine validation output changed • $engineSignature');
        }
        lastRouteErrorSignature = bad.isEmpty ? null : bad;
        lastEngineSignature = engineSignature;
        if (notifications.length > 20) notifications.removeRange(20, notifications.length);
      });
    } catch (e) {
      if (mounted) setState(() {
        error = e.toString().replaceFirst('Exception: ', '');
        notifications.insert(0, '${DateTime.now().toLocal()} • Diagnostics request failed');
        if (notifications.length > 20) notifications.removeLast();
      });
    } finally {
      loading = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> testProviders() async {
    if (testing) return;
    setState(() { testing = true; });
    try {
      final result = await api.testAIProviders().timeout(const Duration(seconds: 24));
      if (!mounted) return;
      final checks = (result['checks'] as List? ?? const []).whereType<Map>().toList();
      final messages = checks.where((c) => c['provider'] == 'gemini' || c['provider'] == 'openai' || c['provider'] == 'openrouter').map((c) {
        final name = (c['provider'] ?? 'AI').toString().toUpperCase();
        final verdict = (c['verdict'] ?? 'WAIT').toString().toUpperCase();
        final status = (c['status'] ?? 'unknown').toString();
        final latency = c['latency_ms'] == null ? '—' : '${c['latency_ms']} ms';
        return '$name • $status • $verdict • $latency';
      }).toList();
      setState(() {
        providerResult = result;
        for (final message in messages.reversed) {
          notifications.insert(0, '${DateTime.now().toLocal()} • AI validation • $message');
        }
        if (notifications.length > 20) notifications.removeRange(20, notifications.length);
      });
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(messages.isEmpty ? (result['message'] ?? 'AI test completed').toString() : messages.join('\n'))));
    } catch (e) {
      if (mounted) {
        setState(() {
          providerResult = {'status': 'failed', 'message': e.toString()};
          notifications.insert(0, '${DateTime.now().toLocal()} • AI provider test failed');
          if (notifications.length > 20) notifications.removeLast();
        });
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('AI provider validation failed. See notification log.')));
      }
    } finally {
      if (mounted) setState(() { testing = false; });
    }
  }

  Widget metric(String title, String value, {String? detail}) => Card(
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(color: Colors.white70, fontSize: 11)),
        const SizedBox(height: 5),
        Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: Color(0xFF12D6FF))),
        if (detail != null) Padding(padding: const EdgeInsets.only(top: 4), child: Text(detail, style: const TextStyle(fontSize: 10, color: Colors.white60))),
      ]),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final signalBuild = Map<String, dynamic>.from(diagnostics['signal_build'] as Map? ?? const {});
    final serverRoutes = Map<String, dynamic>.from(diagnostics['api_performance'] as Map? ?? const {});
    final clientRoutes = FreshApi.requestMetrics;
    final aiChecks = (providerResult['checks'] as List? ?? const []).whereType<Map>().where((c) => c['provider'] == 'openai' || c['provider'] == 'openrouter').toList();
    return RefreshIndicator(
      onRefresh: refresh,
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          const Text('FLOW MONITOR • API SPEED • ENGINE VALIDATION', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
          const SizedBox(height: 5),
          const Text('Measured client/server timings, bytes, error counts and provider outputs. Green means an actual request succeeded; missing measurements are never filled with sample values.', style: TextStyle(color: Colors.white70, fontSize: 12)),
          if (error != null) Card(child: ListTile(leading: const Icon(Icons.error_outline, color: Colors.orangeAccent), title: const Text('Diagnostics unavailable'), subtitle: Text(error!))),
          GridView.count(
            crossAxisCount: 2, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), childAspectRatio: 1.8,
            children: [
              metric('Signal build', fmt(signalBuild['last_duration_ms'], ' ms'), detail: 'Completed cycles: ${signalBuild['build_count'] ?? 0}'),
              metric('Refresh state', signalBuild['in_flight'] == true ? 'RUNNING' : 'IDLE', detail: 'Background refresh; no blocking HTTP wait'),
              metric('Backend route count', '${serverRoutes.length}', detail: 'Routes observed by middleware'),
              metric('Client route count', '${clientRoutes.length}', detail: 'Routes observed by this app process'),
            ],
          ),
          const SizedBox(height: 8),
          const Text('SERVER API ROUTE METRICS', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          if (serverRoutes.isEmpty) const Card(child: Padding(padding: EdgeInsets.all(12), child: Text('No route measurements returned yet. Refresh after the app has made API requests.'))),
          for (final entry in serverRoutes.entries.toList()..sort((a, b) => a.key.compareTo(b.key)))
            Card(child: ListTile(
              dense: true,
              leading: Icon(((entry.value as Map)['last_status'] is num && ((entry.value as Map)['last_status'] as num) >= 400) ? Icons.error_outline : Icons.speed,
                  color: ((entry.value as Map)['last_status'] is num && ((entry.value as Map)['last_status'] as num) >= 400) ? Colors.orangeAccent : Colors.greenAccent),
              title: Text(entry.key, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
              subtitle: Text('Last ${fmt((entry.value as Map)['last_ms'], ' ms')} • avg ${fmt((entry.value as Map)['average_ms'], ' ms')} • status ${(entry.value as Map)['last_status'] ?? '—'}\n${fmt((entry.value as Map)['last_response_bytes'], ' B')} response • ${fmt((entry.value as Map)['last_server_throughput_bytes_per_second'], ' B/s')} • errors ${(entry.value as Map)['errors'] ?? 0}', style: const TextStyle(fontSize: 10)),
            )),
          const SizedBox(height: 8),
          const Text('ANDROID CLIENT REQUEST METRICS', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          if (clientRoutes.isEmpty) const Card(child: Padding(padding: EdgeInsets.all(12), child: Text('Client request metrics will appear after screens make HTTP calls.'))),
          for (final entry in clientRoutes.entries.toList()..sort((a, b) => a.key.compareTo(b.key)))
            Card(child: ListTile(
              dense: true,
              title: Text(entry.key, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
              subtitle: Text('Last ${fmt(entry.value['last_ms'], ' ms')} • avg ${fmt(entry.value['average_ms'], ' ms')} • status ${entry.value['last_status'] ?? '—'}\nRequest ${fmt(entry.value['last_request_bytes'], ' B')} → response ${fmt(entry.value['last_response_bytes'], ' B')} • ${fmt(entry.value['last_client_throughput_bytes_per_second'], ' B/s')} • errors ${entry.value['errors'] ?? 0}', style: const TextStyle(fontSize: 10)),
            )),
          const SizedBox(height: 8),
          const Text('ORDER FLOW WEBSOCKET TRANSPORT', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          Builder(builder: (context) {
            final ws = OrderFlowTelemetry.latest;
            if (ws.isEmpty) {
              return const Card(child: Padding(padding: EdgeInsets.all(12), child: Text('Open the Order Flow tab to collect WebSocket payload speed and quote-age measurements.')));
            }
            return Card(child: Column(children: [
              ListTile(leading: const Icon(Icons.swap_horiz, color: Color(0xFF12D6FF)), title: Text('Mode: ${ws['mode'] ?? 'wait'}'), subtitle: Text('Latest payload ${fmt(ws['payload_bytes'], ' B')} • ${fmt(ws['bytes_per_second'], ' B/s')} • ${fmt(ws['messages_per_second'], ' msg/s')}')),
              ListTile(dense: true, title: const Text('Quote freshness', style: TextStyle(fontSize: 11)), subtitle: Text('Age ${fmt(ws['quote_age_ms'], ' ms')} • inter-message ${fmt(ws['inter_message_ms'], ' ms')}')),
              ListTile(dense: true, title: const Text('Source timestamp', style: TextStyle(fontSize: 11)), subtitle: Text('${ws['source_timestamp'] ?? 'not available'}')),
              ListTile(dense: true, title: const Text('Depth semantics', style: TextStyle(fontSize: 11)), subtitle: Text('${ws['level_semantics'] ?? 'No broker depth metadata received'}')),
            ]));
          }),
          const SizedBox(height: 8),
          const Text('PER-INDEX ENGINE VALIDATION TIMINGS', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          for (final entry in (Map<String, dynamic>.from(signalsPayload['signals'] as Map? ?? const {})).entries)
            Builder(builder: (context) {
              final row = Map<String, dynamic>.from(entry.value as Map? ?? const {});
              final perf = Map<String, dynamic>.from(row['performance'] as Map? ?? const {});
              final engine = Map<String, dynamic>.from(row['five_layer_engine'] as Map? ?? row['quant_engine'] as Map? ?? const {});
              final layers = Map<String, dynamic>.from(engine['layers'] as Map? ?? row['layers'] as Map? ?? const {});
              final passed = layers.values.whereType<Map>().where((x) => x['pass'] == true).length;
              final blocked = (row['reasons'] as List? ?? row['reason'] as List? ?? const []).map((x) => x.toString()).take(3).join(' • ');
              return Card(child: ListTile(
                dense: true,
                leading: Icon((row['decision'] == 'CALL BUY' || row['decision'] == 'PUT BUY') ? Icons.check_circle : Icons.hourglass_empty,
                    color: (row['decision'] == 'CALL BUY' || row['decision'] == 'PUT BUY') ? Colors.greenAccent : Colors.orangeAccent),
                title: Text('${entry.key} • ${row['decision'] ?? 'WAIT'} • $passed/${layers.length} layers', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
                subtitle: Text('Index snapshot ${fmt(perf['index_snapshot_ms'], ' ms')} • five-layer validation ${fmt(perf['five_layer_validation_ms'], ' ms')}${blocked.isEmpty ? '' : '\nBlocked: $blocked'}', style: const TextStyle(fontSize: 10)),
              ));
            }),
          const SizedBox(height: 8),
          const Text('GEMINI + OPENAI + OPENROUTER DATA VALIDATION', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          FilledButton.icon(onPressed: testing ? null : testProviders, icon: testing ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.verified_outlined), label: Text(testing ? 'TESTING PROVIDERS…' : 'TEST GEMINI + OPENAI + OPENROUTER')),
          if (providerResult.isNotEmpty) Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Overall status: ${providerResult['status'] ?? 'unknown'}', style: const TextStyle(fontWeight: FontWeight.w900)),
            Text((providerResult['message'] ?? '').toString(), style: const TextStyle(fontSize: 11, color: Colors.white70)),
            for (final check in aiChecks)
              Padding(padding: const EdgeInsets.only(top: 10), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${(check['provider'] ?? '').toString().toUpperCase()} • ${check['model'] ?? '—'}', style: const TextStyle(fontWeight: FontWeight.w800, color: Color(0xFF12D6FF))),
                Text('Status: ${check['status'] ?? 'not_configured'} • HTTP success: ${check['ok'] ?? false} • verdict: ${check['verdict'] ?? 'WAIT'} • latency: ${fmt(check['latency_ms'], ' ms')}'),
                if (check['output'] != null) Text('Output: ${check['output']}', style: const TextStyle(fontSize: 11)),
                if (check['error'] != null) Text('Error: ${check['error']}', style: const TextStyle(color: Colors.orangeAccent, fontSize: 11)),
                if (check['reason'] != null) Text('Reason: ${check['reason']}', style: const TextStyle(fontSize: 11)),
              ])),
          ]))),
          const SizedBox(height: 8),
          const Text('IN-APP NOTIFICATIONS', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          if (notifications.isEmpty) const Card(child: Padding(padding: EdgeInsets.all(12), child: Text('No errors or AI-validation notifications observed in this session.'))),
          for (final note in notifications.take(20)) Card(child: ListTile(leading: const Icon(Icons.notifications_active_outlined, color: Color(0xFF12D6FF)), title: Text(note, style: const TextStyle(fontSize: 11)))),
          const SizedBox(height: 8),
          const Text('AI output is secondary evidence only. It cannot override missing/stale market data, deterministic five-layer checks or risk gates; no live order is placed by this monitor.', style: TextStyle(color: Colors.white70, fontSize: 11)),
        ],
      ),
    );
  }
}
