import 'dart:math' as math;

/// Fail-closed client guard for the external backend's server-owned signal contract.
///
/// This code never starts or advances a stability timer. It only preserves an
/// already-confirmed server decision when the response includes fresh, consistent
/// evidence for the session, five Quant layers, option contract and 600-second gate.
const int requiredSignalStabilitySeconds = 600;
const Duration _maxEvidenceAge = Duration(seconds: 120);
const Set<String> _buyDecisions = {'CALL BUY', 'PUT BUY'};
const List<String> _requiredLayers = [
  'data_quality',
  'trend_sentiment',
  'order_flow',
  'option_selection',
  'risk_levels',
];

Map<String, dynamic> _map(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

String _text(dynamic value) => value is String ? value.trim() : '';

bool _positive(dynamic value) =>
    value is num && value.isFinite && value > 0;

DateTime? _timestamp(dynamic value) {
  if (value is! String || value.trim().isEmpty) return null;
  return DateTime.tryParse(value)?.toUtc();
}

bool _fresh(dynamic value, DateTime now) {
  final timestamp = _timestamp(value);
  if (timestamp == null) return false;
  final age = now.toUtc().difference(timestamp);
  return !age.isNegative && age <= _maxEvidenceAge;
}

bool _sameText(dynamic left, dynamic right) =>
    left is String && left.isNotEmpty && left == right;

bool _trustedSession(dynamic value, DateTime now) {
  final session = _map(value);
  return session['authority'] == 'exchange-calendar' &&
      (session['exchange'] == 'NSE' || session['exchange'] == 'BSE') &&
      session['is_open'] == true &&
      session['is_holiday'] == false &&
      (session['session_type'] == 'REGULAR' ||
          session['session_type'] == 'SPECIAL') &&
      _text(session['session_id']).isNotEmpty &&
      _fresh(session['checked_at_utc'], now);
}

bool _hasFiveLayerEvidence(dynamic value, DateTime now) {
  final engine = _map(value);
  if (engine['data_fresh'] != true || !_fresh(engine['timestamp'], now)) {
    return false;
  }
  final layers = _map(engine['layers']);
  if (layers.length != _requiredLayers.length ||
      !_requiredLayers.every(layers.containsKey)) {
    return false;
  }
  return _requiredLayers.every((key) {
    final layer = _map(layers[key]);
    final detail =
        _text(layer['detail'] ?? layer['reason'] ?? layer['message']);
    return _text(layer['status']).toUpperCase() == 'PASS' &&
        detail.isNotEmpty &&
        _fresh(layer['timestamp'], now) &&
        _map(layer['input_provenance']).isNotEmpty;
  });
}

bool _hasServerConfirmation(
  Map<String, dynamic> signal,
  dynamic engineValue,
  DateTime now,
) {
  final root = _map(signal['signal_stability']);
  final nested = _map(_map(engineValue)['confirmation']);
  final candidateId = _text(signal['candidate_id']);
  final rootRequired = root['required_seconds'];
  final nestedRequired = nested['required_seconds'];
  final rootElapsed = root['elapsed_seconds'];
  final nestedElapsed = nested['elapsed_seconds'];

  return root['state'] == 'CONFIRMED' &&
      nested['state'] == 'CONFIRMED' &&
      root['server_confirmed'] == true &&
      nested['server_confirmed'] == true &&
      _positive(rootRequired) &&
      rootRequired >= requiredSignalStabilitySeconds &&
      _positive(nestedRequired) &&
      nestedRequired >= requiredSignalStabilitySeconds &&
      rootRequired == nestedRequired &&
      _positive(rootElapsed) &&
      rootElapsed >= requiredSignalStabilitySeconds &&
      _positive(nestedElapsed) &&
      nestedElapsed >= requiredSignalStabilitySeconds &&
      rootElapsed == nestedElapsed &&
      candidateId.isNotEmpty &&
      _sameText(root['candidate_id'], candidateId) &&
      _sameText(nested['candidate_id'], candidateId) &&
      _fresh(root['confirmed_at_utc'], now) &&
      _sameText(root['confirmed_at_utc'], nested['confirmed_at_utc']);
}

bool _expiryIsValid(
  Map<String, dynamic> signal,
  Map<String, dynamic> contract,
  DateTime now,
) {
  final expiry = _text(signal['expiry']);
  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(expiry) ||
      expiry != _text(contract['expiry'])) {
    return false;
  }
  final parsed = DateTime.tryParse('${expiry}T00:00:00Z');
  if (parsed == null || parsed.toIso8601String().substring(0, 10) != expiry) {
    return false;
  }
  final istNow = now.toUtc().add(const Duration(hours: 5, minutes: 30));
  final istDate =
      '${istNow.year.toString().padLeft(4, '0')}-${istNow.month.toString().padLeft(2, '0')}-${istNow.day.toString().padLeft(2, '0')}';
  return expiry.compareTo(istDate) >= 0;
}

/// Returns true only when this signal already carries a valid backend decision.
bool isServerConfirmedSignal(
  dynamic signalValue, {
  dynamic marketSession,
  DateTime? now,
}) {
  final currentTime = (now ?? DateTime.now()).toUtc();
  final signal = _map(signalValue);
  final decision = _text(signal['decision']).toUpperCase();
  if (!_buyDecisions.contains(decision) ||
      signal['data_fresh'] != true ||
      !_fresh(signal['timestamp'], currentTime) ||
      signal['price_basis'] != 'OPTION_PREMIUM') {
    return false;
  }

  final expectedSide = decision == 'CALL BUY' ? 'CE' : 'PE';
  if (signal['option_side'] != expectedSide ||
      !_trustedSession(marketSession, currentTime)) {
    return false;
  }

  final validation = _map(signal['live_validation']);
  final blocks = validation['blocks'];
  final guards = signal['guards'];
  if (_text(validation['verdict']).toUpperCase() != 'PASS' ||
      _text(validation['decision']).toUpperCase() != decision ||
      blocks is! List ||
      blocks.isNotEmpty ||
      guards is! List ||
      guards.isNotEmpty) {
    return false;
  }

  final strike = signal['strike'];
  final entry = signal['entry'];
  final stopLoss = signal['stop_loss'];
  final target = signal['target'];
  if (!_positive(strike) ||
      !_positive(entry) ||
      !_positive(stopLoss) ||
      !_positive(target) ||
      !(stopLoss < entry && entry < target)) {
    return false;
  }

  final contract = _map(signal['option_contract']);
  if (_text(contract['symbol']).isEmpty ||
      _text(contract['instrument_token']).isEmpty ||
      contract['option_side'] != expectedSide ||
      !_positive(contract['premium']) ||
      !_fresh(contract['quote_timestamp'], currentTime) ||
      !_expiryIsValid(signal, contract, currentTime)) {
    return false;
  }
  final tolerance = math.max(0.05, (entry as num).toDouble() * 0.01);
  if (((contract['premium'] as num).toDouble() - entry).abs() > tolerance) {
    return false;
  }

  final engineValue = signal['quant_engine'] ?? signal['five_layer_engine'];
  return _hasFiveLayerEvidence(engineValue, currentTime) &&
      _hasServerConfirmation(signal, engineValue, currentTime);
}

Map<String, dynamic> _blockBuy(dynamic signalValue, String blocker) {
  final signal = _map(signalValue);
  final decision = _text(signal['decision']).toUpperCase();
  final candidate = _buyDecisions.contains(decision)
      ? decision
      : _text(signal['candidate_decision']).toUpperCase();
  if (_buyDecisions.contains(candidate)) signal['candidate_decision'] = candidate;
  signal['decision'] = 'WAIT';
  signal['signal_stability'] = <String, dynamic>{
    'state': 'NOT_ACTIONABLE',
    'required_minutes': 10,
    'required_seconds': requiredSignalStabilitySeconds,
    'server_confirmed': false,
  };

  final validation = _map(signal['live_validation']);
  final oldBlocks = validation['blocks'] is List
      ? (validation['blocks'] as List)
          .whereType<String>()
          .toList()
      : <String>[];
  validation['verdict'] = 'WARN';
  validation['decision'] = 'WAIT';
  validation['blocks'] = <String>{...oldBlocks, blocker}.toList();
  signal['live_validation'] = validation;

  final priorSignalBlockers = signal['signal_blockers'] is List
      ? (signal['signal_blockers'] as List).whereType<String>()
      : const <String>[];
  signal['signal_blockers'] =
      <String>{...priorSignalBlockers, blocker}.toList();
  signal['server_decision_verified'] = false;
  return signal;
}

/// Forces every unproven BUY candidate to WAIT and removes its trade plan.
Map<String, dynamic> enforceServerOwnedSignalConfirmation(
  Map<String, dynamic> response, {
  DateTime? now,
}) {
  final currentTime = (now ?? DateTime.now()).toUtc();
  final result = Map<String, dynamic>.from(response);
  final session = result['market_session'];
  final rawSignals = _map(result['signals']);
  final guardedSignals = <String, dynamic>{};

  for (final entry in rawSignals.entries) {
    final signal = _map(entry.value);
    final decision = _text(signal['decision']).toUpperCase();
    final candidate = _text(signal['candidate_decision']).toUpperCase();
    final hasBuy =
        _buyDecisions.contains(decision) || _buyDecisions.contains(candidate);
    final confirmed =
        isServerConfirmedSignal(signal, marketSession: session, now: currentTime);
    if (hasBuy && !confirmed) {
      guardedSignals[entry.key] = _blockBuy(
        signal,
        'Server-owned session, Quant evidence, option contract or 600-second confirmation is missing, stale, inconsistent, or failed.',
      );
    } else {
      guardedSignals[entry.key] = <String, dynamic>{
        ...signal,
        'server_decision_verified': confirmed,
      };
    }
  }
  result['signals'] = guardedSignals;

  final plans = result['trade_plans'];
  if (plans is List) {
    final confirmedIndexes = guardedSignals.entries
        .where((entry) => isServerConfirmedSignal(
              entry.value,
              marketSession: session,
              now: currentTime,
            ))
        .map((entry) => entry.key.toUpperCase())
        .toSet();
    final filtered = plans.where((plan) {
      final row = _map(plan);
      final index = _text(row['index']).toUpperCase();
      final candidateId = _text(row['candidate_id']);
      final signal = guardedSignals.entries
          .where((entry) => entry.key.toUpperCase() == index)
          .map((entry) => entry.value)
          .cast<Map<String, dynamic>?>()
          .firstWhere((value) => value != null, orElse: () => null);
      return confirmedIndexes.contains(index) &&
          signal != null &&
          candidateId.isNotEmpty &&
          candidateId == signal['candidate_id'];
    }).toList();
    result['trade_plans'] = filtered;
    result['qualified_trade_count'] = filtered.length;
  } else {
    result['trade_plans'] = <dynamic>[];
    result['qualified_trade_count'] = 0;
  }
  return result;
}
