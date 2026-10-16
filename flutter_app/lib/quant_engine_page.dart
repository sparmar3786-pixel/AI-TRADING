import 'package:flutter/material.dart';

/// Separate, read-only view of the backend's five-layer quant validation.
/// Missing engine fields are shown as DATA REQUIRED; this page never fabricates PASS.
class QuantEnginePage extends StatelessWidget {
  const QuantEnginePage({
    required this.selectedIndex,
    required this.signals,
    required this.market,
    required this.onIndexChanged,
    super.key,
  });

  final String selectedIndex;
  final Map<String, dynamic> signals;
  final Map<String, dynamic> market;
  final ValueChanged<String> onIndexChanged;

  static const _expectedLayers = <String>[
    'Data freshness',
    'Trend & sentiment',
    'Order-flow validation',
    'Option selection & liquidity',
    'Risk & 10-minute stability',
  ];

  Map<String, dynamic> _map(dynamic value) =>
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

  @override
  Widget build(BuildContext context) {
    final signal = _map(signals[selectedIndex]);
    final engine = _map(signal['quant_engine'] ?? signal['five_layer_engine']);
    final rawLayers = engine['layers'] ?? engine['layer_results'] ?? signal['quant_layers'];
    final parsedLayers = <Map<String, dynamic>>[];
    if (rawLayers is List) {
      for (final item in rawLayers) {
        if (item is Map) parsedLayers.add(Map<String, dynamic>.from(item));
      }
    } else if (rawLayers is Map) {
      for (final entry in rawLayers.entries) {
        if (entry.value is Map) {
          parsedLayers.add(<String, dynamic>{'name': entry.key.toString(), ...Map<String, dynamic>.from(entry.value as Map)});
        } else {
          parsedLayers.add(<String, dynamic>{'name': entry.key.toString(), 'status': entry.value});
        }
      }
    }
    final allowedStatuses = {'PASS', 'WARN', 'FAIL', 'BLOCK', 'UNAVAILABLE'};
    final exactlyFiveLayers = parsedLayers.length == _expectedLayers.length;
    final layersSchemaValid = exactlyFiveLayers && parsedLayers.every((layer) {
      final status = (layer['status'] ?? layer['verdict'] ?? '').toString().toUpperCase();
      final detail = (layer['detail'] ?? layer['reason'] ?? layer['message'] ?? '').toString().trim();
      return allowedStatuses.contains(status) && detail.isNotEmpty;
    });
    final engineTimestamp = DateTime.tryParse((engine['timestamp'] ?? '').toString());
    final engineAge = engineTimestamp == null ? null : DateTime.now().difference(engineTimestamp).inSeconds;
    final engineFresh = engine['data_fresh'] == true &&
        engineAge != null && engineAge >= 0 && engineAge <= 120;
    final dataAvailable = layersSchemaValid && engineFresh;
    final allLayersPass = dataAvailable && parsedLayers.every(
      (layer) => (layer['status'] ?? layer['verdict'] ?? '').toString().toUpperCase() == 'PASS',
    );
    final reportedStatus = (engine['decision'] ?? engine['verdict'] ?? engine['status'] ?? 'WAIT').toString().toUpperCase();
    final confirmation = _map(engine['confirmation'] ?? signal['signal_stability']);
    final stabilityState = (confirmation['state'] ?? 'NOT VERIFIED').toString().toUpperCase();
    final candidateConfirmed = {'CALL BUY', 'PUT BUY'}.contains(reportedStatus) &&
        allLayersPass && stabilityState == 'CONFIRMED';
    final anyLayerBlocked = parsedLayers.any((layer) =>
        {'FAIL', 'BLOCK'}.contains((layer['status'] ?? layer['verdict'] ?? '').toString().toUpperCase()));
    final engineStatus = !dataAvailable ? 'DATA REQUIRED'
        : (reportedStatus == 'BLOCK' || anyLayerBlocked ? 'BLOCK'
        : (candidateConfirmed ? 'PASS' : 'WAIT'));
    final marketRow = _map(market[selectedIndex]);
    final live = marketRow['live'] == true;
    final age = marketRow['age_seconds'];

    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const Text('5-LAYER QUANT ENGINE', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
        const SizedBox(height: 5),
        const Text(
          'Independent validation tab. Parmar strategies remain separate; this engine is a validation gate, not a second signal generator.',
          style: TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              DropdownButtonFormField<String>(
                value: selectedIndex,
                decoration: const InputDecoration(labelText: 'Index'),
                items: const ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX']
                    .map((v) => DropdownMenuItem<String>(value: v, child: Text(v))).toList(),
                onChanged: (value) { if (value != null) onIndexChanged(value); },
              ),
              const SizedBox(height: 10),
              Row(children: [
                const Expanded(child: Text('Quant validation status', style: TextStyle(fontWeight: FontWeight.w800))),
                Text(engineStatus, style: TextStyle(
                  fontWeight: FontWeight.w900,
                  color: engineStatus == 'PASS' ? Colors.greenAccent : engineStatus == 'BLOCK' ? Colors.redAccent : Colors.orangeAccent,
                )),
              ]),
              const SizedBox(height: 6),
              Text('Market feed: ${live ? 'LIVE' : 'NOT VERIFIED'} • Snapshot age: ${age == null ? 'unknown' : '$age sec'}',
                style: TextStyle(color: live ? Colors.greenAccent : Colors.orangeAccent, fontSize: 12)),
              Text('600-second stability gate: $stabilityState • required ${confirmation['required_seconds'] ?? 600} sec',
                style: TextStyle(color: stabilityState == 'CONFIRMED' ? Colors.greenAccent : Colors.orangeAccent, fontSize: 12)),
              if (!dataAvailable) ...[
                const SizedBox(height: 10),
                const Text(
                  'Backend must provide exactly five layer results, a fresh timestamp (within 120 seconds), data_fresh=true, and a reason for each layer. Otherwise results remain DATA REQUIRED.',
                  style: TextStyle(color: Colors.orangeAccent),
                ),
              ],
            ]),
          ),
        ),
        const SizedBox(height: 8),
        for (var i = 0; i < _expectedLayers.length; i++)
          _LayerCard(
            number: i + 1,
            expectedName: _expectedLayers[i],
            data: dataAvailable && i < parsedLayers.length ? parsedLayers[i] : null,
          ),
        const SizedBox(height: 8),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(12),
            child: Text(
              'Safety rule: any missing/stale input, failed layer, conflicting validation or incomplete 600-second stability gate must remain WAIT/BLOCK. This tab does not place orders and does not claim accuracy or profitability.',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
        ),
      ],
    );
  }
}

class _LayerCard extends StatelessWidget {
  const _LayerCard({required this.number, required this.expectedName, required this.data});
  final int number;
  final String expectedName;
  final Map<String, dynamic>? data;

  @override
  Widget build(BuildContext context) {
    final name = (data?['name'] ?? data?['layer_name'] ?? expectedName).toString();
    final status = (data?['status'] ?? data?['verdict'] ?? 'DATA REQUIRED').toString().toUpperCase();
    final score = data?['score'];
    final detail = (data?['detail'] ?? data?['reason'] ?? data?['message'] ?? 'Backend layer evidence not supplied.').toString();
    final color = status == 'PASS' ? Colors.greenAccent
        : (status == 'FAIL' || status == 'BLOCK' ? Colors.redAccent : Colors.orangeAccent);
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            CircleAvatar(radius: 13, child: Text('$number', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w900))),
            const SizedBox(width: 9),
            Expanded(child: Text(name, style: const TextStyle(fontWeight: FontWeight.w800))),
            Text(score == null ? status : '$score/100 • $status',
              style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w900)),
          ]),
          const SizedBox(height: 7),
          Text(detail, style: const TextStyle(color: Colors.white70, fontSize: 12)),
        ]),
      ),
    );
  }
}
