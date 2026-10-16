/// Client-side actionability contract for the single authoritative backend
/// stability gate. The backend already confirms the exact side, strike, and
/// expiry candidate continuously for 600 seconds. The client independently
/// rejects non-live/stale payloads and verifies the backend's confirmation.
Map<String, dynamic> applyServerSignalSafetyGate(Map<String, dynamic> response) {
  final result = Map<String, dynamic>.from(response);
  final rawSignals = Map<String, dynamic>.from(result['signals'] as Map? ?? const {});
  final market = Map<String, dynamic>.from(result['market'] as Map? ?? const {});
  final responseLive = result['live'] == true;
  final accepted = <String>{};

  for (final entry in rawSignals.entries) {
    final index = entry.key.toString().toUpperCase();
    final row = Map<String, dynamic>.from(entry.value as Map? ?? const {});
    final decision = (row['decision'] ?? 'WAIT').toString().trim().toUpperCase();
    final validation = Map<String, dynamic>.from(row['live_validation'] as Map? ?? const {});
    final stability = Map<String, dynamic>.from(row['signal_stability'] as Map? ?? const {});
    final guards = (row['guards'] as List?) ?? const <dynamic>[];
    final marketRow = Map<String, dynamic>.from((market[entry.key] ?? market[index]) as Map? ?? const {});
    final strike = _safeFiniteNumber(row['strike']);
    final entryPrice = _safeFiniteNumber(row['entry']);
    final stop = _safeFiniteNumber(row['stop_loss']);
    final target = _safeFiniteNumber(row['target']);
    final optionSide = (row['option_side'] ?? '').toString().trim().toUpperCase();
    final expiry = (row['expiry'] ?? '').toString().trim();
    final expiryDate = DateTime.tryParse(expiry);
    final wantsAction = decision == 'CALL BUY' || decision == 'PUT BUY';
    final sideMatches = decision == 'CALL BUY'
        ? optionSide == 'CE'
        : decision == 'PUT BUY'
            ? optionSide == 'PE'
            : false;

    final reasons = <String>[];
    if (!responseLive) reasons.add('Backend response is not marked live');
    if (marketRow['live'] != true) reasons.add('Matching index market quote is not live');
    if (row['data_fresh'] != true) reasons.add('Signal data-quality gate is not PASS');
    if (validation['verdict'] != 'PASS') reasons.add('Backend live validation is not PASS');
    if (stability['state'] != 'CONFIRMED') reasons.add('Backend 10-minute confirmation is not CONFIRMED');
    if (guards.isNotEmpty) reasons.add('Signal contains active guards');
    if (!sideMatches) reasons.add('Decision and option side do not match');
    if (strike == null || strike <= 0) reasons.add('Strike is missing or invalid');
    if (expiryDate == null) reasons.add('Option expiry is missing or invalid');
    if (entryPrice == null || entryPrice <= 0 || stop == null || target == null ||
        stop <= 0 || !(stop < entryPrice && entryPrice < target)) {
      reasons.add('Entry, stop-loss and target do not form valid positive long-option risk levels');
    }

    final actionable = wantsAction && reasons.isEmpty;
    if (!actionable) {
      // A WAIT/blocked response must never leak active levels from an earlier
      // setup. Diagnostic candidate metadata is not used as an active trade.
      for (final key in const [
        'strike', 'expiry', 'entry', 'exit', 'stop_loss', 'target',
        'option_type', 'option_side',
      ]) {
        row[key] = null;
      }
      final planValue = row['trade_plan'];
      if (planValue is Map) {
        final plan = Map<String, dynamic>.from(planValue);
        plan['selection_grade'] = 'WAIT';
        for (final key in const ['strike', 'expiry', 'entry', 'exit', 'stop_loss', 'target']) {
          plan[key] = null;
        }
        row['trade_plan'] = plan;
      }
      if (wantsAction) {
        row['decision'] = 'WAIT';
        validation['decision'] = 'WAIT';
        validation['verdict'] = 'BLOCKED';
        final blocks = List<dynamic>.from(validation['blocks'] as List? ?? const []);
        blocks.addAll(reasons.map((reason) => 'CLIENT_SAFETY_GATE: $reason'));
        validation['blocks'] = blocks.map((value) => value.toString()).toSet().toList();
        row['live_validation'] = validation;
      }
      final currentState = (stability['state'] ?? '').toString();
      final blockedState = (!responseLive || marketRow['live'] != true || row['data_fresh'] != true)
          ? 'BLOCKED_STALE_OR_UNVERIFIED_DATA'
          : (currentState.isNotEmpty && currentState != 'CONFIRMED'
              ? currentState
              : 'NOT_ACTIONABLE');
      row['signal_stability'] = <String, dynamic>{
        ...stability,
        'state': blockedState,
        'required_minutes': 10,
      };
    } else {
      accepted.add(index);
      row['signal_stability'] = <String, dynamic>{
        ...stability,
        'state': 'CONFIRMED',
        'required_minutes': 10,
      };
    }
    rawSignals[entry.key] = row;
  }

  final plans = (result['trade_plans'] as List? ?? const [])
      .whereType<Map>()
      .map((plan) => Map<String, dynamic>.from(plan))
      .where((plan) {
        final index = (plan['index'] ?? '').toString().toUpperCase();
        if (!accepted.contains(index)) return false;
        final signalValue = rawSignals[index];
        if (signalValue is! Map) return false;
        final signal = Map<String, dynamic>.from(signalValue);
        final planDecision = (plan['decision'] ?? plan['side'] ?? '').toString().toUpperCase();
        if (planDecision != (signal['decision'] ?? '').toString().toUpperCase()) return false;
        if (_safeFiniteNumber(plan['strike']) != _safeFiniteNumber(signal['strike'])) return false;
        final planExpiry = (plan['expiry'] ?? '').toString();
        final signalExpiry = (signal['expiry'] ?? '').toString();
        if (planExpiry.length < 10 || signalExpiry.length < 10 ||
            planExpiry.substring(0, 10) != signalExpiry.substring(0, 10)) return false;
        for (final field in const ['entry', 'stop_loss', 'target']) {
          final a = _safeFiniteNumber(plan[field]);
          final b = _safeFiniteNumber(signal[field]);
          if (a == null || b == null || (a - b).abs() > 0.0001) return false;
        }
        return true;
      }).toList();

  result['signals'] = rawSignals;
  result['trade_plans'] = plans;
  result['qualified_trade_count'] = plans.length;
  return result;
}

double? _safeFiniteNumber(dynamic value) {
  final parsed = value is num ? value.toDouble() : double.tryParse(value?.toString() ?? '');
  if (parsed == null || !parsed.isFinite) return null;
  return parsed;
}
