import 'package:flutter/material.dart';

/// Separate, read-only view of the backend's five-layer quant validation.
/// Missing engine fields are shown as DATA REQUIRED; this page never fabricates PASS.
class QuantEnginePage extends StatelessWidget {
  const QuantEnginePage({
    required this.selectedIndex,
    required this.signals,
    required this.market,
    required this.onIndexChanged,
    this.marketOpen = true,
    super.key,
  });

  final String selectedIndex;
  final Map<String, dynamic> signals;
  final Map<String, dynamic> market;
  final ValueChanged<String> onIndexChanged;
  final bool marketOpen;

  static const _expectedLayers = <String>[
    'Data freshness',
    'Trend & sentiment',
    'Order-flow validation',
    'Option selection & liquidity',
    'Risk & 10-minute stability',
  ];

  Map<String, dynamic> _map(dynamic value) =>
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

  int _layerCount(dynamic value) =>
      value is List ? value.length : value is Map ? value.length : 0;

  @override
  Widget build(BuildContext context) {
    final signal = _map(signals[selectedIndex]);
    final engine = _map(signal['quant_engine'] ?? signal['five_layer_engine']);
    // Prefer a complete five-layer contract from the engine, but tolerate the
    // canonical raw layer map returned by older backend builds. An empty or
    // partial nested object must not mask a complete sibling payload.
    final layerCandidates = <dynamic>[
      engine['layers'], engine['layer_results'], signal['quant_layers'], signal['layers'],
    ];
    final rawLayers = layerCandidates.firstWhere(
      (candidate) => _layerCount(candidate) == _expectedLayers.length,
      orElse: () => layerCandidates.firstWhere(
        (candidate) => _layerCount(candidate) > 0,
        orElse: () => null,
      ),
    );
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
    // Raw quant_engine.py layers use `pass` + `reason`; map that explicit
    // result to a display status without ever promoting missing evidence.
    for (final layer in parsedLayers) {
      if (layer['status'] == null && layer['verdict'] == null && layer['pass'] is bool) {
        if (layer['pass'] == true) {
          layer['status'] = 'PASS';
        } else {
          final evidence = (layer['detail'] ?? layer['reason'] ?? layer['message'] ?? '')
              .toString().toLowerCase();
          final unavailable = RegExp(r'unavailable|missing|not supplied|not available|insufficient|unknown|required')
              .hasMatch(evidence);
          layer['status'] = unavailable ? 'UNAVAILABLE' : 'FAIL';
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
    final hasEngineTimestamp = engineTimestamp != null;
    final dataAvailable = layersSchemaValid && engineFresh;
    final allLayersPass = dataAvailable && parsedLayers.every(
      (layer) => (layer['status'] ?? layer['verdict'] ?? '').toString().toUpperCase() == 'PASS',
    );
    final reportedStatus = (engine['decision'] ?? engine['verdict'] ?? engine['status'] ?? 'WAIT').toString().toUpperCase();
    // Prefer server-owned stability metadata and merge the nested layer summary.
    // A CONFIRMED label alone is insufficient if the 600-second timer cannot be verified.
    final rootStability = _map(signal['signal_stability']);
    final nestedConfirmation = _map(engine['confirmation']);
    final confirmation = <String, dynamic>{
      ...rootStability,
      ...nestedConfirmation,
    };
    final stabilityState = (confirmation['state'] ?? 'NOT VERIFIED').toString().toUpperCase();
    final rootRequiredSeconds = (rootStability['required_seconds'] as num?)?.toInt() ?? 0;
    final nestedRequiredSeconds = (nestedConfirmation['required_seconds'] as num?)?.toInt() ?? 0;
    final requiredSeconds = nestedRequiredSeconds;
    final stabilityStateConsistent = rootStability.isNotEmpty &&
        nestedConfirmation.isNotEmpty &&
        (rootStability['state'] ?? '').toString().toUpperCase() ==
            (nestedConfirmation['state'] ?? '').toString().toUpperCase();
    final sinceUtc = DateTime.tryParse((rootStability['since_utc'] ?? '').toString());
    final elapsedSeconds = sinceUtc == null
        ? null
        : DateTime.now().toUtc().difference(sinceUtc.toUtc()).inSeconds;
    final timerVerified = stabilityStateConsistent &&
        rootRequiredSeconds >= 600 &&
        nestedRequiredSeconds >= 600 &&
        rootRequiredSeconds == nestedRequiredSeconds &&
        elapsedSeconds != null && elapsedSeconds >= nestedRequiredSeconds;
    final candidateConfirmed = {'CALL BUY', 'PUT BUY'}.contains(reportedStatus) &&
        allLayersPass && stabilityState == 'CONFIRMED' && timerVerified;
    final anyLayerBlocked = parsedLayers.any((layer) =>
        {'FAIL', 'BLOCK'}.contains((layer['status'] ?? layer['verdict'] ?? '').toString().toUpperCase()));
    final engineStatus = !layersSchemaValid || !hasEngineTimestamp || engineAge == null || engineAge < 0 || engineAge > 120
        ? 'DATA REQUIRED'
        : (!engineFresh || reportedStatus == 'BLOCK' || anyLayerBlocked
            ? 'BLOCK'
            : (candidateConfirmed ? 'PASS' : 'WAIT'));
    final reasons = signal['reasons'];
    final fallbackReason = reasons is List
        ? reasons.where((item) => item != null && item.toString().trim().isNotEmpty).map((item) => item.toString()).join(' • ')
        : (signal['reason'] ?? signal['error'] ?? 'Backend did not return per-layer evidence.').toString();
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
              Text('Market feed: ${!marketOpen ? 'MARKET CLOSED' : (live ? 'LIVE' : 'NOT VERIFIED')} • Last snapshot age: ${age == null ? 'unknown' : '$age sec'}',
                style: TextStyle(color: marketOpen && live ? Colors.greenAccent : Colors.orangeAccent, fontSize: 12)),
              Text(
                '600-second stability gate: $stabilityState • ${elapsedSeconds == null ? 'timer unverified' : '$elapsedSeconds / $requiredSeconds sec'}',
                style: TextStyle(
                  color: stabilityState == 'CONFIRMED' && timerVerified
                      ? Colors.greenAccent : Colors.orangeAccent,
                  fontSize: 12,
                ),
              ),
              if (stabilityState == 'CONFIRMED' && !timerVerified)
                const Text(
                  'Backend says CONFIRMED, but the 600-second timer evidence is missing, too short, or future-dated. Kept at WAIT.',
                  style: TextStyle(color: Colors.orangeAccent, fontSize: 12),
                ),
              if (!dataAvailable) ...[
                const SizedBox(height: 10),
                Text(
                  !layersSchemaValid
                      ? 'Backend did not supply exactly five complete layer results. Details: $fallbackReason'
                      : (!hasEngineTimestamp
                          ? 'Backend engine timestamp is missing. Details: $fallbackReason'
                          : (engineAge != null && (engineAge < 0 || engineAge > 120)
                              ? 'Backend engine timestamp is future-dated or older than 120 seconds. Details: $fallbackReason'
                              : 'Market evidence failed freshness validation. Review the layer reasons below. $fallbackReason')),
                  style: const TextStyle(color: Colors.orangeAccent),
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
            data: layersSchemaValid && i < parsedLayers.length ? parsedLayers[i] : null,
            fallbackDetail: fallbackReason,
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
  const _LayerCard({required this.number, required this.expectedName, required this.data, required this.fallbackDetail});
  final int number;
  final String expectedName;
  final Map<String, dynamic>? data;
  final String fallbackDetail;

  @override
  Widget build(BuildContext context) {
    final name = (data?['name'] ?? data?['layer_name'] ?? expectedName).toString();
    final status = (data?['status'] ?? data?['verdict'] ?? 'DATA REQUIRED').toString().toUpperCase();
    final score = data?['score'];
    final detail = (data?['detail'] ?? data?['reason'] ?? data?['message'] ?? (fallbackDetail.isEmpty ? 'Backend layer evidence not supplied.' : fallbackDetail)).toString();
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
