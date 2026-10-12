import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('Angel One signal routes use the dedicated service', () async {
    Uri? requestedUri;
    final client = MockClient((request) async {
      requestedUri = request.url;
      return http.Response(jsonEncode({'authenticated': false}), 200);
    });
    addTearDown(client.close);

    final api = FreshApi(
      'https://legacy.example.test',
      client,
      'https://signals.example.test',
    );
    await api.angelStatus();
    expect(requestedUri!.origin, 'https://signals.example.test');
    expect(requestedUri!.path, '/v1/angel/status');
  });

  test('Cloud AI remains on the legacy backend', () async {
    Uri? requestedUri;
    final client = MockClient((request) async {
      requestedUri = request.url;
      return http.Response(jsonEncode({'answer': 'test response'}), 200);
    });
    addTearDown(client.close);

    final api = FreshApi(
      'https://legacy.example.test',
      client,
      'https://signals.example.test',
    );
    await api.aiChat(index: 'NIFTY', question: 'test');
    expect(requestedUri!.origin, 'https://legacy.example.test');
    expect(requestedUri!.path, '/v1/ai/chat');
  });

  test('signals keeps query parameters separate from the path', () async {
    Uri? requestedUri;
    final client = MockClient((request) async {
      requestedUri = request.url;
      return http.Response(
        jsonEncode({'ok': true, 'market': <String, dynamic>{}}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    addTearDown(client.close);

    final api = FreshApi('https://example.test', client, 'https://example.test');
    await api.signals(emaFast: 8, emaSlow: 13);

    expect(requestedUri, isNotNull);
    expect(requestedUri!.path, '/v1/signals');
    expect(requestedUri!.queryParameters, {
      'ema_fast': '8',
      'ema_slow': '13',
    });
    expect(requestedUri!.toString(),
        'https://example.test/v1/signals?ema_fast=8&ema_slow=13');
  });
}
