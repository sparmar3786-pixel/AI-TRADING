import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/api.dart';
import 'package:ai_trading_signal/config.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
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

    final api = FreshApi.signal(client);
    await api.signals(emaFast: 8, emaSlow: 21);

    expect(requestedUri, isNotNull);
    expect(requestedUri!.host, Uri.parse(AppConfig.signalBackendUrl).host);
    expect(requestedUri!.path, '/v1/signals');
    expect(requestedUri!.queryParameters, {
      'ema_fast': '8',
      'ema_slow': '21',
    });
    expect(requestedUri!.toString(),
        '${AppConfig.signalBackendUrl}/v1/signals?ema_fast=8&ema_slow=21');
  });
  test('generic GET routes use the injected client', () async {
    Uri? requestedUri;
    final client = MockClient((request) async {
      requestedUri = request.url;
      return http.Response(
        jsonEncode({'authenticated': false}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    addTearDown(client.close);

    final api = FreshApi.signal(client);
    await api.angelStatus();

    expect(requestedUri?.path, '/v1/angel/status');
    expect(requestedUri?.host, Uri.parse(AppConfig.signalBackendUrl).host);
  });

  test('Angel connect health check and POST use the injected client', () async {
    final methods = <String>[];
    final paths = <String>[];
    final client = MockClient((request) async {
      methods.add(request.method);
      paths.add(request.url.path);
      return http.Response(
        jsonEncode({'ok': true}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    addTearDown(client.close);

    final api = FreshApi.signal(client);
    await api.connectAngel({
      'angel_api_key': 'test-key',
      'angel_client_code': 'test-client',
      'angel_pin': '1234',
      'angel_totp': '123456',
    });

    expect(methods, ['GET', 'POST']);
    expect(paths, ['/health', '/v1/angel/connect']);
  });

}
