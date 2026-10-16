import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/signal_safety_gate.dart';

Map<String, dynamic> _response({
  bool live = true,
  bool marketLive = true,
  bool dataFresh = true,
  String decision = 'CALL BUY',
  String validation = 'PASS',
  String stability = 'CONFIRMED',
  String optionSide = 'CE',
  double entry = 100,
  double stop = 80,
  double target = 140,
  String expiry = '2026-10-29',
  List<dynamic> guards = const [],
}) {
  return <String, dynamic>{
    'live': live,
    'market': <String, dynamic>{'NIFTY': <String, dynamic>{'live': marketLive, 'age_seconds': 1, 'ltp': 25000}},
    'signals': <String, dynamic>{
      'NIFTY': <String, dynamic>{
        'decision': decision,
        'candidate_decision': decision,
        'data_fresh': dataFresh,
        'option_side': optionSide,
        'option_type': optionSide == 'CE' ? 'CALL' : 'PUT',
        'strike': 25000,
        'expiry': expiry,
        'entry': entry,
        'stop_loss': stop,
        'target': target,
        'exit': target,
        'guards': guards,
        'live_validation': <String, dynamic>{'verdict': validation, 'decision': decision, 'blocks': <String>[]},
        'signal_stability': <String, dynamic>{'state': stability, 'required_minutes': 10},
        'trade_plan': <String, dynamic>{
          'selection_grade': 'A', 'strike': 25000, 'expiry': expiry,
          'entry': entry, 'exit': target, 'stop_loss': stop, 'target': target,
        },
      },
    },
    'trade_plans': <Map<String, dynamic>>[
      <String, dynamic>{
        'index': 'NIFTY', 'side': decision, 'strike': 25000,
        'expiry': expiry, 'entry': entry, 'stop_loss': stop, 'target': target,
      },
    ],
    'qualified_trade_count': 1,
  };
}

void main() {
  test('retains levels only for a live, fresh, validated, server-confirmed signal', () {
    final result = applyServerSignalSafetyGate(_response());
    final signal = (result['signals'] as Map)['NIFTY'] as Map;
    expect(signal['decision'], 'CALL BUY');
    expect(signal['strike'], 25000);
    expect(signal['expiry'], '2026-10-29');
    expect(signal['signal_stability']['state'], 'CONFIRMED');
    expect(result['trade_plans'], hasLength(1));
    expect(result['qualified_trade_count'], 1);
  });

  test('stale top-level response cannot expose an actionable setup', () {
    final result = applyServerSignalSafetyGate(_response(live: false));
    final signal = (result['signals'] as Map)['NIFTY'] as Map;
    expect(signal['decision'], 'WAIT');
    expect(signal['strike'], isNull);
    expect(signal['expiry'], isNull);
    expect(signal['entry'], isNull);
    expect(signal['stop_loss'], isNull);
    expect(signal['target'], isNull);
    expect(result['trade_plans'], isEmpty);
    expect(result['qualified_trade_count'], 0);
  });

  test('stale index quote and failed data freshness independently block action', () {
    for (final response in [_response(marketLive: false), _response(dataFresh: false)]) {
      final result = applyServerSignalSafetyGate(response);
      final signal = (result['signals'] as Map)['NIFTY'] as Map;
      expect(signal['decision'], 'WAIT');
      expect(signal['entry'], isNull);
      expect(result['trade_plans'], isEmpty);
    }
  });

  test('requires backend confirmation, passing validation and no guards', () {
    for (final response in [
      _response(stability: 'CONFIRMING'),
      _response(validation: 'WARN'),
      _response(guards: ['stale quote']),
    ]) {
      final result = applyServerSignalSafetyGate(response);
      final signal = (result['signals'] as Map)['NIFTY'] as Map;
      expect(signal['decision'], 'WAIT');
      expect(signal['strike'], isNull);
      expect(result['trade_plans'], isEmpty);
    }
  });

  test('rejects mismatched option side and invalid risk ordering', () {
    for (final response in [
      _response(optionSide: 'PE'),
      _response(entry: 100, stop: 110, target: 140),
    ]) {
      final result = applyServerSignalSafetyGate(response);
      final signal = (result['signals'] as Map)['NIFTY'] as Map;
      expect(signal['decision'], 'WAIT');
      expect(signal['entry'], isNull);
      expect(result['trade_plans'], isEmpty);
    }
  });

  test('rejects old trade plan whose expiry differs from the confirmed signal', () {
    final response = _response();
    (response['trade_plans'] as List).first['expiry'] = '2026-11-05';
    final result = applyServerSignalSafetyGate(response);
    final signal = (result['signals'] as Map)['NIFTY'] as Map;
    expect(signal['decision'], 'CALL BUY');
    expect(signal['strike'], 25000);
    expect(result['trade_plans'], isEmpty);
    expect(result['qualified_trade_count'], 0);
  });

  test('WAIT cannot retain old levels copied from a prior setup', () {
    final result = applyServerSignalSafetyGate(_response(decision: 'WAIT', stability: 'CONFIRMING'));
    final signal = (result['signals'] as Map)['NIFTY'] as Map;
    expect(signal['decision'], 'WAIT');
    expect(signal['strike'], isNull);
    expect(signal['expiry'], isNull);
    expect(signal['entry'], isNull);
    expect(signal['stop_loss'], isNull);
    expect(signal['target'], isNull);
    expect(result['trade_plans'], isEmpty);
  });
  test('selected-index live badge does not borrow freshness from another index', () {
    expect(isSelectedIndexFeedLive(
      apiOnline: true, signalsEndpointOnline: true, marketOpen: true,
      marketRow: <String, dynamic>{'live': false, 'age_seconds': 1},
    ), isFalse);
    expect(isSelectedIndexFeedLive(
      apiOnline: true, signalsEndpointOnline: true, marketOpen: true,
      marketRow: <String, dynamic>{'live': true, 'age_seconds': 61},
    ), isFalse);
    expect(isSelectedIndexFeedLive(
      apiOnline: true, signalsEndpointOnline: true, marketOpen: true,
      marketRow: <String, dynamic>{'live': true, 'age_seconds': 1},
    ), isTrue);
  });

}
