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
    final api = FreshApi('https://legacy.example.test', client, 'https://signals.example.test');
    await api.angelStatus();
    expect(requestedUri!.origin, 'https://signals.example.test');
    expect(requestedUri!.path, '/v1/angel/status');
  });

  test('Health checks the FreshApi instance base URL', () async {
    Uri? requestedUri;
    final client = MockClient((request) async {
      requestedUri = request.url;
      return http.Response(jsonEncode({'status': 'ok'}), 200);
    });
    addTearDown(client.close);
    final api = FreshApi('https://legacy.example.test', client, 'https://signals.example.test');
    await api.health();
    expect(requestedUri!.origin, 'https://legacy.example.test');
    expect(requestedUri!.path, '/health');
  });

  test('Portfolio and paper ledger use the AI-TRADING signal service', () async {
    final requested = <Uri>[];
    final client = MockClient((request) async {
      requested.add(request.url);
      return http.Response(jsonEncode({'status': 'ok', 'trades': []}), 200);
    });
    addTearDown(client.close);
    final api = FreshApi('https://legacy.example.test', client, 'https://signals.example.test');
    await api.portfolio();
    await api.paperTrades();
    await api.paperReport();
    expect(requested.map((uri) => uri.origin), everyElement('https://signals.example.test'));
    expect(requested.map((uri) => uri.path), [
      '/v1/portfolio',
      '/v1/paper/trades',
      '/v1/paper/report',
    ]);
  });

  test('Angel One connect health-checks and posts to the signal service', () async {
    final requested = <http.Request>[];
    final client = MockClient((request) async {
      requested.add(request);
      return http.Response(jsonEncode({'status': 'ok'}), 200);
    });
    addTearDown(client.close);
    final api = FreshApi('https://legacy.example.test', client, 'https://signals.example.test');
    await api.connectAngel({'angel_api_key': 'test'});
    expect(requested[0].url.origin, 'https://signals.example.test');
    expect(requested[0].url.path, '/health');
    expect(requested[1].url.origin, 'https://signals.example.test');
    expect(requested[1].url.path, '/v1/angel/connect');
  });

  test('Cloud AI chat uses the AI-TRADING signal service', () async {
    Uri? requestedUri;
    final client = MockClient((request) async {
      requestedUri = request.url;
      return http.Response(jsonEncode({'answer': 'test response'}), 200);
    });
    addTearDown(client.close);
    final api = FreshApi('https://legacy.example.test', client, 'https://signals.example.test');
    await api.aiChat(index: 'NIFTY', question: 'test');
    expect(requestedUri!.origin, 'https://signals.example.test');
    expect(requestedUri!.path, '/v1/ai/chat');
  });

  test('NVIDIA-only review uses the dedicated signal-service route', () async {
    Uri? requestedUri;
    final client = MockClient((request) async {
      requestedUri = request.url;
      return http.Response(jsonEncode({'answer': 'test response'}), 200);
    });
    addTearDown(client.close);
    final api = FreshApi('https://legacy.example.test', client, 'https://signals.example.test');
    await api.nvidiaChat(index: 'NIFTY', question: 'test');
    expect(requestedUri!.origin, 'https://signals.example.test');
    expect(requestedUri!.path, '/v1/ai/nvidia-chat');
  });

  test('Search provider checks and Kumo routes use the AI-TRADING service', () async {
    final requested = <http.Request>[];
    final client = MockClient((request) async {
      requested.add(request);
      return http.Response(jsonEncode({'status': 'ok', 'ready': true}), 200);
    });
    addTearDown(client.close);
    final api = FreshApi('https://legacy.example.test', client, 'https://signals.example.test');
    await api.postJson('/v1/providers/search/status', {});
    await api.postJson('/v1/providers/search/test', {});
    await api.kumoStatus();
    await api.kumoPredict({'model': 'kumo-tabular'});
    expect(requested.map((request) => request.url.origin), everyElement('https://signals.example.test'));
    expect(requested.map((request) => request.url.path), [
      '/v1/providers/search/status',
      '/v1/providers/search/test',
      '/v1/ai/kumo/status',
      '/v1/ai/kumo/predict',
    ]);
    expect(jsonDecode(requested.last.body)['request']['model'], 'kumo-tabular');
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
