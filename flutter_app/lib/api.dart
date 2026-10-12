import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'config.dart';

class FreshApi {
  FreshApi([String? baseUrl, http.Client? client, String? signalBaseUrl])
      : baseUrl = baseUrl ?? AppConfig.backendUrl,
        signalBackendUrl = signalBaseUrl ?? AppConfig.signalBackendUrl,
        _testClient = client;

  static const FlutterSecureStorage _secureStorage = FlutterSecureStorage();

  final String baseUrl;
  final String signalBackendUrl;
  // Injectable only for tests; production requests keep using package:http's
  // shared top-level client so periodic refreshes do not leak client instances.
  final http.Client? _testClient;

  static const Set<String> _signalRoutes = <String>{
    '/health',
    '/v1/system/diagnostics',
    '/v1/metadata',
    '/v1/angel/status',
    '/v1/angel/connect',
    '/v1/instruments/sync',
    '/v1/stream/start',
    '/v1/live/status',
    '/v1/market/ticks',
    '/v1/option-chain',
    '/v1/market/sentiment',
    '/v1/signals',
    '/api/v1/signals',
    '/api/signals',
    '/v1/backtest/historical',
  };

  Uri _uri(String path) {
    final suffix = path.startsWith('/') ? path : '/' + path;
    final suffixUri = Uri.parse(suffix);
    final routeBase = _signalRoutes.contains(suffixUri.path) ? signalBackendUrl : baseUrl;
    var normalized = routeBase.trim();
    while (normalized.endsWith('/')) {
      normalized = normalized.substring(0, normalized.length - 1);
    }
    final parsed = Uri.tryParse(normalized);
    if (parsed == null || parsed.scheme != 'https' || parsed.host.isEmpty ||
        parsed.userInfo.isNotEmpty || parsed.hasQuery || parsed.hasFragment ||
        parsed.host == 'localhost' || parsed.host == '127.0.0.1' || parsed.host == '10.0.2.2') {
      throw Exception('Backend must be configured with a valid public HTTPS URL.');
    }
    var basePath = parsed.path;
    while (basePath.endsWith('/')) {
      basePath = basePath.substring(0, basePath.length - 1);
    }
    return parsed.replace(
      path: basePath + suffixUri.path,
      query: suffixUri.hasQuery ? suffixUri.query : null,
    );
  }

  Future<String> _deviceId() async {
    // Keep the same device scope used by older APKs so server-side Angel One
    // sessions remain linked across upgrades. Prefer the existing prefs value;
    // if only the newer secure-storage value exists, migrate it back unchanged.
    final prefs = await SharedPreferences.getInstance();
    var id = prefs.getString('fresh_device_id');
    if (id == null || id.length < 43) {
      try {
        final secureId = await _secureStorage.read(key: 'fresh_device_id');
        if (secureId != null && secureId.length >= 43) {
          id = secureId;
          await prefs.setString('fresh_device_id', id);
        }
      } catch (_) {
        // Secure storage can be unavailable after an Android restore/update;
        // continue with the stable legacy ID if present or create one below.
      }
    }
    if (id == null || id.length < 43) {
      final bytes = List<int>.generate(32, (_) => Random.secure().nextInt(256));
      id = base64UrlEncode(bytes).replaceAll('=', '');
      await prefs.setString('fresh_device_id', id);
    }
    return id;
  }

  Future<Map<String, String>> _headers() async => {
        'accept': 'application/json',
        'content-type': 'application/json',
        'X-Device-Id': await _deviceId(),
      };

  Future<Map<String, dynamic>> getJson(
    String path, {
    Duration timeout = const Duration(seconds: 30),
  }) async {
    final uri = _uri(path);
    final headers = await _headers();
    final response = await (_testClient == null
            ? http.get(uri, headers: headers)
            : _testClient!.get(uri, headers: headers))
        .timeout(timeout);
    return _decode(response);
  }

  Future<Map<String, dynamic>> postJson(
    String path,
    Map<String, dynamic> body, {
    Duration timeout = const Duration(seconds: 30),
  }) async {
    final uri = _uri(path);
    final headers = await _headers();
    final encodedBody = jsonEncode(body);
    final response = await (_testClient == null
            ? http.post(uri, headers: headers, body: encodedBody)
            : _testClient!.post(uri, headers: headers, body: encodedBody))
        .timeout(timeout);
    return _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    dynamic decoded;
    try {
      decoded = response.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
    } catch (_) {
      throw Exception('Server returned an invalid response (HTTP ${response.statusCode}).');
    }
    if (response.statusCode >= 400) {
      // FastAPI returns a structured "detail" field. Surface a short, safe
      // diagnostic so the app can distinguish route, device-header and broker errors.
      final rawDetail = decoded is Map ? decoded['detail'] : null;
      String detail = '';
      if (rawDetail is String) {
        detail = rawDetail.replaceAll(RegExp(r'[\r\n]+'), ' ').trim();
      } else if (rawDetail is Map) {
        // FastAPI diagnostics may provide structured message/reason/action fields.
        detail = [
          rawDetail['message'],
          rawDetail['reason'],
          rawDetail['action'],
        ].whereType<String>().where((value) => value.trim().isNotEmpty).join(' ');
      } else if (rawDetail is List) {
        detail = rawDetail.whereType<String>().join(' ');
      }
      final safeDetail = detail.length > 400 ? '${detail.substring(0, 400)}…' : detail;
      throw Exception(safeDetail.isEmpty
          ? 'Request failed (HTTP ${response.statusCode}). Check backend route and server logs.'
          : 'HTTP ${response.statusCode}: $safeDetail');
    }
    if (decoded is! Map) {
      throw Exception('HTTP ${response.statusCode}: invalid JSON response');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<Map<String, dynamic>> health() => getJson('/health');
  Future<Map<String, dynamic>> systemDiagnostics() => getJson('/v1/system/diagnostics');
  Future<Map<String, dynamic>> metadata() => getJson('/v1/metadata');
  Future<Map<String, dynamic>> angelStatus() => getJson('/v1/angel/status');
  Future<Map<String, dynamic>> testAIProviders() =>
      postJson('/v1/providers/ai/test', {});
  Future<Map<String, dynamic>> testSearchProviders() =>
      postJson('/v1/providers/search/test', {});

  Future<Map<String, dynamic>> saveCredentials(
    Map<String, dynamic> body,
  ) =>
      postJson('/v1/settings/credentials', body);

  Future<void> checkBackend() async {
    final uri = _uri('/health');
    final response = await (_testClient == null ? http.get(uri) : _testClient!.get(uri))
        .timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) {
      throw Exception('Backend health check failed: HTTP ${response.statusCode}. Railway service may be down or the domain may be wrong.');
    }
  }

  Future<Map<String, dynamic>> connectAngel(
    Map<String, dynamic> body,
  ) async {
    await checkBackend();
    return postJson('/v1/angel/connect', body);
  }

  Future<Map<String, dynamic>> syncInstruments() =>
      postJson('/v1/instruments/sync', {});

  Future<Map<String, dynamic>> startStream(List<String> indexes) =>
      postJson('/v1/stream/start', {'indexes': indexes});

  /// Try the canonical route first, then legacy aliases used by older
  /// Railway deployments. Only fall back for HTTP 404; authentication,
  /// broker and server errors must remain visible to the UI.
  Future<Map<String, dynamic>> signals({int emaFast = 8, int emaSlow = 13}) async {
    final query = Uri(queryParameters: {
      'ema_fast': '$emaFast',
      'ema_slow': '$emaSlow',
    }).query;
    final routes = <String>[
      '/v1/signals?$query',
      '/api/v1/signals?$query',
      '/api/signals?$query',
    ];
    String? last404;
    for (final route in routes) {
      final uri = _uri(route);
      final headers = await _headers();
      final response = await (_testClient == null
              ? http.get(uri, headers: headers)
              : _testClient.get(uri, headers: headers))
          .timeout(const Duration(seconds: 30));
      if (response.statusCode == 404) {
        last404 = 'HTTP 404 from ${Uri.parse(signalBackendUrl).host}${route.split('?').first}';
        continue;
      }
      return _decode(response);
    }
    throw Exception(last404 ??
        'Signal API route not found. Check Railway backend deployment and routes.');
  }

  Future<Map<String, dynamic>> liveExecutionStatus() => getJson('/v1/live/status');


  Future<Map<String, dynamic>> portfolio() => getJson('/v1/portfolio');

  /// Actual broker tick-store snapshot; empty ticks are reported as empty,
  /// never replaced with generated sample data.
  Future<Map<String, dynamic>> marketTicks() => getJson('/v1/market/ticks');

  Future<Map<String, dynamic>> paperTrades() => getJson('/v1/paper/trades');
  Future<Map<String, dynamic>> paperReport() => getJson('/v1/paper/report');

  Future<Map<String, dynamic>> openPaperTrade({
    required String tradeId,
    required String strategyId,
    required String index,
    required String side,
    required String regime,
    double slippageR = 0.02,
    double transactionCostR = 0.02,
    String notes = '',
  }) => postJson('/v1/paper/trades/open', {
        'trade_id': tradeId,
        'strategy_id': strategyId,
        'index': index,
        'side': side,
        'regime': regime,
        'slippage_r': slippageR,
        'transaction_cost_r': transactionCostR,
        'notes': notes,
      });

  Future<Map<String, dynamic>> closePaperTrade({
    required String tradeId,
    required double grossR,
    String notes = '',
  }) => postJson('/v1/paper/trades/${Uri.encodeComponent(tradeId)}/close', {
        'gross_r': grossR,
        'notes': notes,
      });

  /// Gemini + configured cloud fallback can take longer than a normal JSON call.
  /// Keep this separate from offline Qwen, which runs directly on the handset.
  Future<Map<String, dynamic>> aiChat({
    required String index,
    required String question,
    List<Map<String, String>> history = const [],
  }) => postJson(
        '/v1/ai/chat',
        {
          'index': index,
          'question': question,
          'history': history,
        },
        timeout: const Duration(seconds: 40),
      );

  /// Historical candle fetches are bounded server-side to 45 seconds.
  Future<Map<String, dynamic>> historicalBacktest(
    Map<String, dynamic> body,
  ) => postJson(
        '/v1/backtest/historical',
        body,
        timeout: const Duration(seconds: 55),
      );
}
