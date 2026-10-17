import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/signal_confirmation.dart';

void main() {
  final now = DateTime.utc(2026, 10, 19, 4, 30);
  final recent = now.subtract(const Duration(seconds: 15)).toIso8601String();
  const candidateId = 'NIFTY-CALL-20261029-25000-001';

  Map<String, dynamic> fixture() {
    final layers = <String, dynamic>{
      'data_quality': {'status': 'PASS', 'detail': 'Fresh Angel One quote', 'timestamp': recent, 'input_provenance': {'source': 'ANGEL_ONE', 'field': 'ltp'}},
      'trend_sentiment': {'status': 'PASS', 'detail': 'Trend aligned', 'timestamp': recent, 'input_provenance': {'source': 'CANDLES', 'field': 'close'}},
      'order_flow': {'status': 'PASS', 'detail': 'Bid/ask pressure valid', 'timestamp': recent, 'input_provenance': {'source': 'ANGEL_ONE', 'field': 'depth'}},
      'option_selection': {'status': 'PASS', 'detail': 'Liquid contract selected', 'timestamp': recent, 'input_provenance': {'source': 'ANGEL_ONE', 'field': 'option_chain'}},
      'risk_levels': {'status': 'PASS', 'detail': 'Premium risk levels valid', 'timestamp': recent, 'input_provenance': {'source': 'RISK_ENGINE', 'field': 'risk_levels'}},
    };
    final confirmation = <String, dynamic>{
      'state': 'CONFIRMED', 'server_confirmed': true, 'required_seconds': 600,
      'elapsed_seconds': 615, 'candidate_id': candidateId, 'confirmed_at_utc': recent,
    };
    return <String, dynamic>{
      'market_session': {
        'authority': 'exchange-calendar', 'exchange': 'NSE', 'is_open': true,
        'is_holiday': false, 'session_type': 'REGULAR', 'special_session': false,
        'session_id': 'NSE:2026-10-19:REGULAR', 'checked_at_utc': recent,
      },
      'signals': {
        'NIFTY': {
          'index': 'NIFTY', 'decision': 'CALL BUY', 'candidate_decision': 'CALL BUY',
          'candidate_id': candidateId, 'timestamp': recent, 'data_fresh': true,
          'strike': 25000, 'option_side': 'CE', 'price_basis': 'OPTION_PREMIUM',
          'entry': 120, 'stop_loss': 110, 'target': 140, 'expiry': '2026-10-29',
          'option_contract': {
            'symbol': 'NIFTY29OCT2625000CE', 'instrument_token': '12345',
            'option_side': 'CE', 'expiry': '2026-10-29', 'premium': 120,
            'quote_timestamp': recent,
          },
          'guards': <dynamic>[],
          'live_validation': {'verdict': 'PASS', 'decision': 'CALL BUY', 'blocks': <dynamic>[]},
          'quant_engine': {'data_fresh': true, 'timestamp': recent, 'layers': layers, 'confirmation': confirmation},
          'signal_stability': {...confirmation, 'required_minutes': 10},
        },
      },
      'trade_plans': [{'index': 'NIFTY', 'candidate_id': candidateId}],
      'qualified_trade_count': 1,
    };
  }

  test('local candidate state cannot confirm BUY without server-owned evidence', () {
    final payload = fixture();
    final signal = (payload['signals'] as Map)['NIFTY'] as Map;
    (signal['signal_stability'] as Map).remove('server_confirmed');
    ((signal['quant_engine'] as Map)['confirmation'] as Map).remove('server_confirmed');
    (signal['signal_stability'] as Map).remove('candidate_id');
    ((signal['quant_engine'] as Map)['confirmation'] as Map).remove('candidate_id');

    final result = enforceServerOwnedSignalConfirmation(payload, now: now);
    final guarded = (result['signals'] as Map)['NIFTY'] as Map;
    expect(guarded['decision'], 'WAIT');
    expect((guarded['signal_stability'] as Map)['server_confirmed'], false);
  });

  test('complete fresh server confirmation and five evidence-backed layers may remain actionable', () {
    final result = enforceServerOwnedSignalConfirmation(fixture(), now: now);
    final guarded = (result['signals'] as Map)['NIFTY'] as Map;
    expect(guarded['decision'], 'CALL BUY');
  });

  test('holiday, missing layer provenance, or mismatched option premium blocks a BUY', () {
    final holiday = fixture();
    (holiday['market_session'] as Map)['is_holiday'] = true;
    expect(((enforceServerOwnedSignalConfirmation(holiday, now: now)['signals'] as Map)['NIFTY'] as Map)['decision'], 'WAIT');

    final missing = fixture();
    final signal = (missing['signals'] as Map)['NIFTY'] as Map;
    (((signal['quant_engine'] as Map)['layers'] as Map)['order_flow'] as Map).remove('input_provenance');
    expect(((enforceServerOwnedSignalConfirmation(missing, now: now)['signals'] as Map)['NIFTY'] as Map)['decision'], 'WAIT');

    final premium = fixture();
    ((premium['signals'] as Map)['NIFTY'] as Map)['entry'] = 150;
    expect(((enforceServerOwnedSignalConfirmation(premium, now: now)['signals'] as Map)['NIFTY'] as Map)['decision'], 'WAIT');
  });
}
