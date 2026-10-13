import 'dart:async';
import 'dart:convert';
import 'dart:ui' show PlatformDispatcher;
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api.dart';
import 'config.dart';
import 'trade_engine_page.dart';
import 'broker_home_prototype_page.dart';
import 'ai_chat_page.dart';
import 'quant_engine_lab_page.dart';
import 'order_flow_page.dart';
import 'strategy_library_page.dart';
import 'flow_monitor_page.dart';
import 'risk_calculator_page.dart';
import 'gemini_signal_review.dart';
import 'background_monitor.dart';
import 'daily_ai_memory.dart';
import 'daily_ai_memory_page.dart';
import 'smc_chart_page.dart';

const tabs = ['Dashboard','Market','Option Chain','OI Lab','Indicators','Signals','Risk','Commodities','Backtesting','API','AI Access','Data Health','API & Railway','Market Diagnostics','Trading Setup','Research Engines','5-Layer Quant Signal Engine','Broker Home','AI Chat','Order Flow','Quant Engine Lab','Strategy Library','Flow Monitor','AI Memory','SMC Pro Chart'];
const indexes = ['NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY','SENSEX','BANKEX'];
const commodityOptionUnderlyings = ['CRUDEOIL','CRUDEOILM','NATURALGAS','NATGASMINI','GOLD','GOLDM','SILVER','SILVERM','COPPER','ZINC','ALUMINIUM','LEAD','NICKEL'];
const optionUnderlyings = [...indexes, ...commodityOptionUnderlyings];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Capture Dart/Flutter errors in logcat so a phone-side crash can be
  // diagnosed without silently swallowing the framework's default handling.
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    debugPrint('FRESH_FLUTTER_ERROR: ${details.exceptionAsString()}');
    if (details.stack != null) debugPrintStack(stackTrace: details.stack);
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    debugPrint('FRESH_PLATFORM_ERROR: $error');
    debugPrintStack(stackTrace: stack);
    return false; // Leave unhandled errors visible to Flutter's runtime.
  };
  await initializeBackgroundMonitor();
  runApp(const FreshApp());
}

class FreshApp extends StatelessWidget {
  const FreshApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'AI Trading Signals',
    theme: ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: const Color(0xFF070B12),
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF12D6FF), brightness: Brightness.dark),
      cardColor: const Color(0xFF101722),
      inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
    ),
    home: const FreshHome(),
  );
}

class FreshHome extends StatefulWidget {
  const FreshHome({super.key});
  @override
  State<FreshHome> createState() => _FreshHomeState();
}

class _FreshHomeState extends State<FreshHome> with WidgetsBindingObserver {
  String backendUrl = AppConfig.backendUrl;
  String signalBackendUrl = AppConfig.signalBackendUrl;
  String selectedIndex = 'NIFTY';
  bool apiOnline = false;
  bool signalsEndpointOnline = false;
  String? signalsFetchError;
  bool angelOnline = false;
  Map<String,dynamic> liveTrading = const {};
  Map<String,dynamic> ai = const {};
  Map<String,dynamic> aiProviderStatus = const {};
  Map<String,dynamic> feed = const {};
  Map<String,dynamic> storeDiagnostics = const {};
  Map<String,dynamic> systemDiagnostics = const {};
  String? systemDiagnosticsError;
  Map<String,dynamic> signals = const {};
  List<dynamic> commodities = const [];
  bool _refreshing = false;
  Map<String,dynamic> market = const {};
  // Shared, per-index option-chain cache lets Option Chain and OI Lab consume
  // the same timestamped broker quotes even when signal qualification fails.
  final Map<String, List<dynamic>> optionChainsByIndex = <String, List<dynamic>>{};
  DateTime? _lastOptionChainFetchAt;
  String? _lastOptionChainIndex;
  String? optionChainError;
  List<dynamic> tradePlans = const [];
  int qualifiedCount = 0;
  String? lastFetch;
  int emaFast = 8;
  int emaSlow = 13;
  String status = 'Connect Angel One from Settings.';
  Timer? _refreshTimer;

  /// Cache is best-effort only: corrupted or outdated local JSON must never
  /// crash refresh or be presented as a live backend response.
  Future<Map<String, dynamic>> _loadCachedSignals() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString('fresh_last_signals');
      if (raw == null || raw.trim().isEmpty) return <String, dynamic>{};
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return <String, dynamic>{};
      return Map<String, dynamic>.from(decoded);
    } catch (_) {
      return <String, dynamic>{};
    }
  }

  /// Actionable candidates must keep the same side and strike for 10 minutes.
  /// Any candidate change or failed validation returns the UI to WAIT. This is
  /// a conservative client-side confirmation gate, not a profit guarantee.
  Future<Map<String, dynamic>> _applyTenMinuteSignalGate(Map<String, dynamic> response) async {
    final prefs = await SharedPreferences.getInstance();
    final result = Map<String, dynamic>.from(response);
    final rawSignals = Map<String, dynamic>.from(result['signals'] as Map? ?? const {});
    final stableIndices = <String>{};
    final now = DateTime.now().toUtc();
    for (final entry in rawSignals.entries) {
      final index = entry.key.toString().toUpperCase();
      final row = Map<String, dynamic>.from(entry.value as Map? ?? const {});
      final decision = (row['decision'] ?? 'WAIT').toString().toUpperCase();
      final validation = Map<String, dynamic>.from(row['live_validation'] as Map? ?? const {});
      final guards = (row['guards'] as List?) ?? const <dynamic>[];
      final isCandidate = (decision == 'CALL BUY' || decision == 'PUT BUY') &&
          row['strike'] != null && row['option_side'] != null &&
          row['entry'] != null && row['stop_loss'] != null && row['target'] != null &&
          validation['verdict'] == 'PASS' && guards.isEmpty;
      final serverStability = Map<String, dynamic>.from(row['signal_stability'] as Map? ?? const {});
      if (isCandidate && row['data_fresh'] == true && serverStability['state'] == 'CONFIRMED') {
        // The server already enforced 600 seconds of continuous market evidence;
        // don't accidentally impose a second ten-minute wait on the same signal.
        stableIndices.add(index);
        row['signal_stability'] = <String, dynamic>{
          ...serverStability,
          'required_minutes': 10,
          'server_confirmed': true,
        };
        rawSignals[entry.key] = row;
        continue;
      }
      final storageKey = 'ai_trading_signal_gate_$index';
      if (!isCandidate) {
        await prefs.remove(storageKey);
        row['signal_stability'] = <String, dynamic>{'state': 'NOT_ACTIONABLE', 'required_minutes': 10};
        rawSignals[entry.key] = row;
        continue;
      }
      final candidateKey = '$decision|${row['strike']}|${row['option_side']}';
      final savedRaw = prefs.getString(storageKey);
      Map<String, dynamic>? saved;
      if (savedRaw != null) {
        try {
          final parsed = jsonDecode(savedRaw);
          if (parsed is Map) saved = Map<String, dynamic>.from(parsed);
        } catch (_) { saved = null; }
      }
      final lastSeen = DateTime.tryParse(saved?['last_seen_utc']?.toString() ?? '')?.toUtc();
      final gapTooLong = lastSeen == null || now.difference(lastSeen).inSeconds > 60;
      if (saved == null || saved['candidate'] != candidateKey || saved['since_utc'] == null || gapTooLong) {
        saved = <String, dynamic>{'candidate': candidateKey, 'since_utc': now.toIso8601String()};
      }
      saved['last_seen_utc'] = now.toIso8601String();
      await prefs.setString(storageKey, jsonEncode(saved));
      final since = DateTime.tryParse(saved['since_utc'].toString())?.toUtc() ?? now;
      final elapsed = now.difference(since).inSeconds;
      final remaining = (600 - elapsed).clamp(0, 600);
      row['candidate_decision'] = decision;
      if (elapsed < 600) {
        row['decision'] = 'WAIT';
        final gatedValidation = Map<String, dynamic>.from(validation);
        gatedValidation['decision'] = 'WAIT';
        gatedValidation['verdict'] = 'WARN';
        final blocks = List<dynamic>.from(gatedValidation['blocks'] as List? ?? const []);
        if (!blocks.any((item) => item.toString().contains('10-minute stability gate'))) {
          blocks.add('10-minute stability gate: candidate must remain unchanged for 600 seconds');
        }
        gatedValidation['blocks'] = blocks;
        row['live_validation'] = gatedValidation;
        row['signal_stability'] = <String, dynamic>{
          'state': 'CONFIRMING', 'required_minutes': 10, 'elapsed_seconds': elapsed,
          'remaining_seconds': remaining, 'since_utc': since.toIso8601String(),
        };
      } else {
        stableIndices.add(index);
        row['signal_stability'] = <String, dynamic>{
          'state': 'CONFIRMED', 'required_minutes': 10, 'elapsed_seconds': elapsed,
          'remaining_seconds': 0, 'since_utc': since.toIso8601String(),
        };
      }
      rawSignals[entry.key] = row;
    }
    result['signals'] = rawSignals;
    final plans = (result['trade_plans'] as List? ?? const [])
        .whereType<Map>()
        .map((plan) => Map<String, dynamic>.from(plan))
        .where((plan) => stableIndices.contains((plan['index'] ?? '').toString().toUpperCase()))
        .toList();
    result['trade_plans'] = plans;
    result['qualified_trade_count'] = plans.length;
    return result;
  }

  /// Cached quotes are display-only; cached BUY/SELL recommendations are never actionable.
  Map<String, dynamic> _makeCachedSignalsNonActionable(Map<String, dynamic> cached) {
    final result = Map<String, dynamic>.from(cached);
    final rawSignals = Map<String, dynamic>.from(result['signals'] as Map? ?? const {});
    for (final entry in rawSignals.entries) {
      final row = Map<String, dynamic>.from(entry.value as Map? ?? const {});
      final decision = (row['decision'] ?? '').toString().toUpperCase();
      if (decision == 'CALL BUY' || decision == 'PUT BUY') {
        row['candidate_decision'] = decision;
        row['decision'] = 'WAIT';
        final validation = Map<String, dynamic>.from(row['live_validation'] as Map? ?? const {});
        validation['decision'] = 'WAIT';
        validation['verdict'] = 'WARN';
        final blocks = List<dynamic>.from(validation['blocks'] as List? ?? const []);
        blocks.add('Backend offline: cached signal is not actionable');
        validation['blocks'] = blocks;
        row['live_validation'] = validation;
        row['signal_stability'] = <String, dynamic>{'state': 'STALE_OFFLINE', 'required_minutes': 10};
        rawSignals[entry.key] = row;
      }
    }
    result['signals'] = rawSignals;
    // Cached snapshots can be shown for continuity, but their old server-side
    // "live" flags must never survive an offline refresh.
    final cachedMarket = Map<String, dynamic>.from(result['market'] as Map? ?? const {});
    for (final entry in cachedMarket.entries) {
      final row = Map<String, dynamic>.from(entry.value as Map? ?? const {});
      row['live'] = false;
      row['feed_mode'] = 'CACHED_OFFLINE';
      row['cached'] = true;
      final chain = (row['option_chain'] as List?) ?? const <dynamic>[];
      row['option_chain'] = chain.whereType<Map>().map((raw) {
        final option = Map<String, dynamic>.from(raw);
        option['live'] = false;
        return option;
      }).toList();
      cachedMarket[entry.key] = row;
    }
    result['market'] = cachedMarket;
    result['live'] = false;
    result['feed'] = <String, dynamic>{...(result['feed'] as Map? ?? const {}), 'connected': false, 'mode': 'CACHED_OFFLINE'};
    result['trade_plans'] = <dynamic>[];
    result['qualified_trade_count'] = 0;
    return result;
  }

  void _saveAiMemory() {
    unawaited(DailyAiMemory.saveSnapshot(
      market: Map<String, dynamic>.from(market),
      signals: Map<String, dynamic>.from(signals),
      commodities: List<dynamic>.from(commodities),
      optionChains: optionChainsByIndex.map((key, value) => MapEntry(key, List<dynamic>.from(value))),
      footprint: Map<String, dynamic>.from(OrderFlowTelemetry.latest),
      aiProviders: Map<String, dynamic>.from(aiProviderStatus),
      aiResults: Map<String, dynamic>.from(ai),
    ));
  }

  Future<void> refresh() async {
    if (_refreshing) return;
    _refreshing = true;
    Map<String, dynamic> latestSystemDiagnostics = const {};
    String? latestSystemDiagnosticsError;
    try {
      // Keep the existing AI/chat backend separate. Market, Angel One, account
      // and paper-ledger routes are dispatched by FreshApi to AI-TRADING.
      final api = FreshApi(backendUrl);
      final signalApi = FreshApi(signalBackendUrl);
      // The AI/chat backend is optional and independent of the Angel One
      // market API. Its health failure must never mark market data offline.
      try {
        await api.health();
      } catch (chatHealthError) {
        debugPrint('AI_CHAT_BACKEND_HEALTH_FAILED: $chatHealthError');
      }
      Map<String,dynamic> a = const {};
      String? angelStatusError;
      try {
        a = await signalApi.angelStatus();
      } catch (e) {
        angelStatusError = e.toString().replaceFirst('Exception: ', '');
      }
      Map<String,dynamic> liveStatus = const {};
      try { liveStatus = await signalApi.liveExecutionStatus(); } catch (_) {}
      Map<String,dynamic> providerStatus = const {};
      try {
        // Cloud AI credentials/status belong to the AI/chat backend; market
        // feed health remains owned by signalApi.
        providerStatus = await api.aiStatus();
        if (providerStatus['providers'] is! Map && providerStatus['provider_health'] is List) {
          final normalized = <String, dynamic>{};
          for (final item in (providerStatus['provider_health'] as List).whereType<Map>()) {
            final name = (item['name'] ?? '').toString().toLowerCase();
            if (!['gemini', 'openrouter'].contains(name)) continue;
            normalized[name] = <String, dynamic>{
              'configured': true,
              'ok': false,
              'status': item['status'] == 'COOLDOWN' ? 'cooldown' : 'configured_not_tested',
              'model': item['model'] ?? item['model_name'] ?? 'not reported',
            };
          }
          for (final name in ['gemini', 'openrouter']) {
            normalized.putIfAbsent(name, () => <String, dynamic>{
              'configured': false, 'ok': false, 'status': 'not_configured', 'model': '—',
            });
          }
          providerStatus['providers'] = normalized;
        }
      } catch (providerError) {
        debugPrint('AI_PROVIDER_STATUS_FAILED: $providerError');
      }
      Map<String,dynamic> s;
      try {
        await signalApi.health();
        s = await signalApi.signals(emaFast: emaFast, emaSlow: emaSlow);
        s = await _applyTenMinuteSignalGate(s);
        // API success is independent of local cache persistence. A full device,
        // oversized cached payload or SharedPreferences write error must not
        // falsely turn a successful Railway response into "API UP • DATA ERROR".
        if (mounted) setState(() { signalsEndpointOnline = true; signalsFetchError = null; });
        try {
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('fresh_last_signals', jsonEncode(s));
        } catch (cacheError) {
          debugPrint('FRESH_SIGNALS_CACHE_WRITE_FAILED: $cacheError');
        }
      } catch (e) {
        if (mounted) setState(() { signalsEndpointOnline = false; signalsFetchError = e.toString().replaceFirst('Exception: ', ''); });
        s = _makeCachedSignalsNonActionable(await _loadCachedSignals());
      }
      // The signal endpoint deliberately fails closed when candles/Greeks are
      // incomplete. Fetch the option chain independently so its valid quotes
      // can still populate Option Chain/OI Lab. Throttle this heavier endpoint.
      final responseMarket = Map<String, dynamic>.from(s['market'] as Map? ?? const {});
      final selectedMarket = Map<String, dynamic>.from(responseMarket[selectedIndex] as Map? ?? const {});
      final embeddedChain = (selectedMarket['option_chain'] as List?) ?? const <dynamic>[];
      if (embeddedChain.isNotEmpty) {
        optionChainsByIndex[selectedIndex] = List<dynamic>.from(embeddedChain);
        optionChainError = null;
      } else {
        final now = DateTime.now();
        final shouldFetchChain = _lastOptionChainIndex != selectedIndex ||
            _lastOptionChainFetchAt == null ||
            now.difference(_lastOptionChainFetchAt!) >= const Duration(seconds: 30);
        if (shouldFetchChain) {
          _lastOptionChainIndex = selectedIndex;
          _lastOptionChainFetchAt = now;
          try {
            final chainResponse = await signalApi.getJson('/v1/option-chain?index=${Uri.encodeQueryComponent(selectedIndex)}', timeout: const Duration(seconds: 35));
            final chainRows = (chainResponse['option_chain'] as List?) ?? const <dynamic>[];
            if (chainRows.isNotEmpty) {
              optionChainsByIndex[selectedIndex] = List<dynamic>.from(chainRows);
              optionChainError = null;
            } else {
              optionChainError = (chainResponse['reason'] ?? 'Broker returned no option-chain quotes yet.').toString();
            }
          } catch (e) {
            optionChainError = e.toString().replaceFirst('Exception: ', '');
          }
        }
      }
      try {
        latestSystemDiagnostics = await signalApi.systemDiagnostics();
        latestSystemDiagnosticsError = null;
      } catch (e) {
        latestSystemDiagnostics = const {};
        latestSystemDiagnosticsError = e.toString().replaceFirst('Exception: ', '');
      }
      if (!mounted) return;
      setState(() {
        apiOnline = true;
        systemDiagnostics = latestSystemDiagnostics;
        systemDiagnosticsError = latestSystemDiagnosticsError;
        angelOnline = a['authenticated'] == true;
        liveTrading = liveStatus;
        aiProviderStatus = providerStatus;
        ai = (s['ai'] as Map?)?.cast<String,dynamic>() ?? {};
        feed = (s['feed'] as Map?)?.cast<String,dynamic>() ?? {};
        storeDiagnostics = (s['store'] as Map?)?.cast<String,dynamic>() ?? {};
        signals = (s['signals'] as Map?)?.cast<String,dynamic>() ?? {};
        market = responseMarket.map((key, value) {
          final row = Map<String, dynamic>.from(value as Map? ?? const {});
          final cachedChain = optionChainsByIndex[key];
          final currentChain = (row['option_chain'] as List?) ?? const <dynamic>[];
          if (currentChain.isEmpty && cachedChain != null) {
            row['option_chain'] = _markOptionRowsFresh(cachedChain, forceStale: row['cached'] == true);
            row['option_chain_source'] = 'independent_timestamped_broker_quote';
          } else if (currentChain.isNotEmpty) {
            row['option_chain'] = _markOptionRowsFresh(currentChain, forceStale: row['cached'] == true);
          }
          return MapEntry(key, row);
        });
        commodities = (s['commodities'] as List?) ?? [];
        tradePlans = ((s['trade_plans'] as List?) ?? const []).whereType<Map>().map((plan) => Map<String, dynamic>.from(plan)).toList();
        qualifiedCount = (s['qualified_trade_count'] as num?)?.toInt() ?? tradePlans.length;
        lastFetch = s['last_fetch']?.toString();
        status = signalsEndpointOnline && s['live'] == true
            ? 'LIVE market feed connected.'
            : (signalsFetchError != null && (s['market'] as Map?)?.isEmpty != false
                ? 'Signal data request failed: $signalsFetchError'
                : (angelStatusError != null
                    ? 'Signal API responded, but Angel One status check failed: $angelStatusError'
                    : (lastFetch != null ? 'LIVE unavailable — showing last fetched market data.' : 'Backend online — waiting for Angel One market data. Check broker credentials and connection status.')));
      });
      _saveAiMemory();
    } catch (e) {
      if (mounted) setState(() { apiOnline = false; signalsEndpointOnline = false; signalsFetchError = e.toString().replaceFirst('Exception: ', ''); systemDiagnostics = const {}; systemDiagnosticsError = e.toString().replaceFirst('Exception: ', ''); });
      final s = _makeCachedSignalsNonActionable(await _loadCachedSignals());
      if (!mounted) return;
      setState(() {
        apiOnline = false;
        signalsEndpointOnline = false;
        systemDiagnostics = const {};
        systemDiagnosticsError = e.toString().replaceFirst('Exception: ', '');
        ai = (s['ai'] as Map?)?.cast<String,dynamic>() ?? {};
        feed = (s['feed'] as Map?)?.cast<String,dynamic>() ?? {};
        storeDiagnostics = (s['store'] as Map?)?.cast<String,dynamic>() ?? {};
        signals = (s['signals'] as Map?)?.cast<String,dynamic>() ?? {};
        market = (s['market'] as Map?)?.cast<String,dynamic>() ?? {};
        commodities = (s['commodities'] as List?) ?? [];
        tradePlans = ((s['trade_plans'] as List?) ?? const []).whereType<Map>().map((plan) => Map<String, dynamic>.from(plan)).toList();
        qualifiedCount = (s['qualified_trade_count'] as num?)?.toInt() ?? tradePlans.length;
        lastFetch = s['last_fetch']?.toString();
        status = lastFetch != null ? 'Backend unavailable — showing last fetched market data. Error: ${signalsFetchError ?? 'request failed'}' : 'Backend offline or unreachable: ${signalsFetchError ?? 'health check failed'}';
      });
      _saveAiMemory();
    } finally {
      _refreshing = false;
    }
  }

  bool get _marketOpenNow {
    final ist = DateTime.now().toUtc().add(const Duration(hours: 5, minutes: 30));
    if (ist.weekday == DateTime.saturday || ist.weekday == DateTime.sunday) return false;
    final minutes = ist.hour * 60 + ist.minute;
    if (commodityOptionUnderlyings.contains(selectedIndex)) {
      // MCX closes at 23:30 IST in standard US time and 23:55 IST during US DST.
      final marchFirst = DateTime(ist.year, 3, 1);
      final marchFirstSunday = marchFirst.add(Duration(days: (7 - marchFirst.weekday) % 7));
      final dstStart = marchFirstSunday.add(const Duration(days: 7));
      final novemberFirst = DateTime(ist.year, 11, 1);
      final dstEnd = novemberFirst.add(Duration(days: (7 - novemberFirst.weekday) % 7));
      final usDst = !ist.isBefore(dstStart) && ist.isBefore(dstEnd);
      final closeMinute = usDst ? 23 * 60 + 55 : 23 * 60 + 30;
      return minutes >= 9 * 60 && minutes <= closeMinute;
    }
    return minutes >= (9 * 60 + 15) && minutes <= (15 * 60 + 30);
  }

  bool get _selectedCommodityLive {
    if (!commodityOptionUnderlyings.contains(selectedIndex)) return false;
    final rows = optionChainsByIndex[selectedIndex] ?? const <dynamic>[];
    final now = DateTime.now();
    for (final value in rows) {
      if (value is! Map) continue;
      final stamp = value['source_timestamp'] ?? value['timestamp'];
      final parsed = DateTime.tryParse(stamp?.toString() ?? '');
      if (parsed == null) continue;
      final age = now.difference(parsed.toLocal()).inSeconds;
      if (age >= -5 && age <= 60) return true;
    }
    return false;
  }

  String get _appBarStatus {
    if (!apiOnline) return "API OFFLINE";
    if (commodityOptionUnderlyings.contains(selectedIndex)) {
      if (!_marketOpenNow) return "API UP • MCX CLOSED";
      if (_selectedCommodityLive) return "API LIVE • MCX";
      if (optionChainError != null) return "API UP • MCX DATA ERROR";
      return "API UP • WAITING MCX DATA";
    }
    if (!signalsEndpointOnline) {
      final error = (signalsFetchError ?? '').toLowerCase();
      if (error.contains('socketexception') ||
          error.contains('failed host lookup') ||
          error.contains('connection refused') ||
          error.contains('connection reset') ||
          error.contains('handshakeexception') ||
          error.contains('network is unreachable')) {
        return "API DISCONNECTED";
      }
      if (error.contains('timeoutexception') || error.contains('timed out') || error.contains('timeout')) {
        return "SIGNALS API TIMEOUT";
      }
      return "SIGNALS API ERROR";
    }
    if (!_marketOpenNow) return "API UP • MARKET CLOSED";
    if (signals['live'] == false) return "API UP • INVALID MARKET DATA";
    if (status == "LIVE market feed connected.") return "API LIVE";
    if (status.startsWith("Backend online")) return "API UP • WAITING DATA";
    if (status.startsWith("LIVE unavailable") || status.startsWith("Signal API responded")) return "API UP • REFRESHING DATA";
    return "API UP • INVALID MARKET DATA";
  }

  String get _dataDiagnosticMessage {
    final parts = <String>[];
    if (signalsFetchError != null && signalsFetchError!.trim().isNotEmpty) {
      parts.add(signalsFetchError!.trim());
    }
    final marketRows = Map<String, dynamic>.from(signals['market'] as Map? ?? const {});
    final marketRow = Map<String, dynamic>.from(marketRows[selectedIndex] as Map? ?? const {});
    final signalRows = Map<String, dynamic>.from(signals['signals'] as Map? ?? const {});
    final signalRow = Map<String, dynamic>.from(signalRows[selectedIndex] as Map? ?? const {});
    final reasons = (signalRow['reasons'] as List?) ?? const <dynamic>[];
    if (parts.isEmpty && reasons.isNotEmpty) parts.add(reasons.first.toString());
    final stamp = marketRow['source_timestamp'] ?? marketRow['timestamp'] ?? marketRow['last_updated'];
    parts.add('Last source tick: ${stamp ?? 'not received'}');
    final age = marketRow['age_seconds'];
    if (age != null) parts.add('Tick age: $age seconds');
    return parts.join(' • ');
  }

  Color get _appBarStatusColor {
    if (_appBarStatus.startsWith("API LIVE")) return Colors.greenAccent;
    if (_appBarStatus == "API OFFLINE" || _appBarStatus == "API DISCONNECTED" ||
        _appBarStatus == "SIGNALS API ERROR") return Colors.redAccent;
    if (_appBarStatus.contains("CLOSED")) return const Color(0xFF94A3B8);
    if (_appBarStatus.contains("INVALID MARKET DATA") || _appBarStatus.contains("TIMEOUT")) return Colors.orangeAccent;
    return Colors.orangeAccent;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    refresh();
    _startRefreshTimer();
  }

  void _startRefreshTimer() {
    if (_refreshTimer?.isActive == true) return;
    _refreshTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted) refresh();
    });
  }

  void _stopRefreshTimer() {
    _refreshTimer?.cancel();
    _refreshTimer = null;
  }

  /// Stop background polling while Android is not showing this screen.
  /// This avoids continuing repeated network/state updates behind another app.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _startRefreshTimer();
      refresh();
    } else {
      _stopRefreshTimer();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _refreshTimer?.cancel();
    super.dispose();
  }

  List<dynamic> _markOptionRowsFresh(List<dynamic> rows, {bool forceStale = false}) {
    final now = DateTime.now().toUtc();
    return rows.whereType<Map>().map((raw) {
      final option = Map<String, dynamic>.from(raw);
      final stamp = DateTime.tryParse((option['source_timestamp'] ?? option['timestamp'] ?? '').toString())?.toUtc();
      final age = stamp == null ? null : now.difference(stamp).inMilliseconds / 1000.0;
      option['age_seconds'] = age;
      option['live'] = !forceStale && age != null && age >= 0 && age <= 60;
      return option;
    }).toList();
  }

  Map<String, dynamic> _signal(String i) {
    final row = Map<String, dynamic>.from(signals[i] as Map? ?? const {});
    final marketRow = _market(i);
    // A blocked strategy must still allow the pages to display independently
    // verified spot indicators/depth; missing signal fields remain WAIT.
    if (row['indicators'] is! Map && marketRow['indicators'] is Map) {
      row['indicators'] = marketRow['indicators'];
    }
    if (row['order_flow'] is! Map && marketRow['order_flow'] is Map) {
      row['order_flow'] = marketRow['order_flow'];
    }
    return row;
  }
  Map<String, dynamic> _market(String i) {
    final row = Map<String, dynamic>.from(market[i] as Map? ?? const {});
    final cachedChain = optionChainsByIndex[i];
    final chain = (row['option_chain'] as List?) ?? const <dynamic>[];
    if (chain.isEmpty && cachedChain != null) {
      row['option_chain'] = _markOptionRowsFresh(cachedChain, forceStale: row['cached'] == true);
      row['option_chain_source'] = 'independent_timestamped_broker_quote';
    } else if (chain.isNotEmpty) {
      row['option_chain'] = _markOptionRowsFresh(chain, forceStale: row['cached'] == true);
    }
    return row;
  }

  @override
  Widget build(BuildContext context) => DefaultTabController(
    length: tabs.length,
    child: Scaffold(
      drawer: Drawer(
        child: SafeArea(
          child: Column(
            children: [
              const ListTile(
                leading: Icon(Icons.auto_graph, color: Color(0xFF12D6FF), size: 32),
                title: Text('AI TRADING SIGNALS', style: TextStyle(fontWeight: FontWeight.w900)),
                subtitle: Text('Trading workspace • Navigation'),
              ),
              const Divider(),
              Expanded(
                child: Builder(
                  builder: (drawerContext) => ListView(
                    children: [
                      for (var i = 0; i < tabs.length; i++)
                        ListTile(
                          key: ValueKey('drawer-tab-${tabs[i]}'),
                          leading: Icon(_tabIcon(i)),
                          title: Text(tabs[i]),
                          selected: DefaultTabController.of(drawerContext).index == i,
                          onTap: () {
                            final controller = DefaultTabController.of(drawerContext);
                            controller.animateTo(i);
                            Navigator.pop(drawerContext);
                          },
                        ),
                    ],
                  ),
                ),
              ),
              const Divider(),
              ListTile(
                leading: Icon(Icons.circle, size: 11, color: apiOnline && signalsEndpointOnline ? Colors.greenAccent : (apiOnline ? Colors.orangeAccent : Colors.redAccent)),
                title: Text(apiOnline && signalsEndpointOnline && status == 'LIVE market feed connected.' ? 'Backend + live data OK' : (apiOnline && signalsEndpointOnline && status.startsWith('Backend online') ? 'Backend up • waiting for market data' : (apiOnline ? 'Backend up • data check needed' : 'Backend offline'))),
                subtitle: const Text('Tap a section above to open it'),
              ),
            ],
          ),
        ),
      ),
      appBar: AppBar(
        leading: Builder(builder: (context) => IconButton(
          key: const ValueKey('open-navigation-menu'),
          tooltip: 'Open navigation menu',
          icon: const Icon(Icons.menu),
          onPressed: () => Scaffold.of(context).openDrawer(),
        )),
        title: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('FRESH', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 2)),
          Text('ALGO SIGNAL', style: TextStyle(fontSize: 11)),
        ]),
        actions: [Padding(padding: const EdgeInsets.only(right:12), child: Row(children: [
          Icon(Icons.circle, size:10, color: _appBarStatusColor), SizedBox(width:5),
          Tooltip(
            message: _dataDiagnosticMessage,
            child: Text(_appBarStatus, style: TextStyle(fontSize:11, color: _appBarStatusColor)),
          ),
        ]))],
        bottom: TabBar(isScrollable: true, tabAlignment: TabAlignment.start, tabs: tabs.map((t)=>Tab(text:t)).toList()),
      ),
      body: TabBarView(children: [
        DashboardPage(index:selectedIndex, connected:status == 'LIVE market feed connected.', status:status, signals:signals, market:market, aiProviders:aiProviderStatus, tradePlans:tradePlans, qualifiedCount:qualifiedCount, lastFetch:lastFetch, onSelected:(v)=>setState(()=>selectedIndex=v)),
        MarketPage(selected:selectedIndex,onChanged:(v)=>setState(()=>selectedIndex=v), signal:_signal(selectedIndex), market:_market(selectedIndex)),
        ChainPage(selected:selectedIndex,onChanged:(v){setState(()=>selectedIndex=v);refresh();}, market:_market(selectedIndex), error:optionChainError),
        OIPage(signals:signals, market:market, commodities:commodities, optionChains:optionChainsByIndex),
        IndicatorsPage(selected:selectedIndex,signal:_signal(selectedIndex),fast:emaFast,slow:emaSlow,onChanged:(f,s){setState((){emaFast=f;emaSlow=s;});refresh();},onIndex:(v)=>setState(()=>selectedIndex=v)),
        SignalPage(backendUrl:backendUrl,liveStatus:liveTrading,index:selectedIndex,signals:signals,ai:ai,aiProviders:aiProviderStatus,tradePlans:tradePlans,market:market,onChanged:(v)=>setState(()=>selectedIndex=v)),
        RiskPage(index:selectedIndex,signal:_signal(selectedIndex),plans:tradePlans,market:market,commodities:commodities),
        CommodityPage(items:commodities),
        BacktestingPage(backendUrl: backendUrl),
        ApiPage(backendUrl:backendUrl,signalBackendUrl:signalBackendUrl,feed:feed,storeDiagnostics:storeDiagnostics,market:market,onSaved:(url){setState(()=>backendUrl=url);refresh();}),
        AiAccessPage(backendUrl:backendUrl),
        DataHealthPage(
          backendUrl: backendUrl,
          signalBackendUrl: signalBackendUrl,
          apiOnline: apiOnline,
          signalsOnline: signalsEndpointOnline,
          angelOnline: angelOnline,
          status: status,
          diagnostics: systemDiagnostics,
          diagnosticsError: systemDiagnosticsError,
          market: market,
          lastFetch: lastFetch,
          onRefresh: refresh,
        ),
        const ApiRailwayPage(),
        MarketDiagnosticsPage(market: market, signals: signals, feed: feed, diagnostics: storeDiagnostics, lastFetch: lastFetch),
        TradingSetupPage(backendUrl: backendUrl, selectedIndex: selectedIndex, aiProviders: aiProviderStatus, apiOnline: apiOnline, signalsOnline: signalsEndpointOnline, angelOnline: angelOnline, market: market, signals: signals, ai: ai, liveStatus: liveTrading, lastFetch: lastFetch),
        ResearchEnginesPage(market: market, signals: signals, ai: ai, commodities: commodities, optionChains: optionChainsByIndex, lastFetch: lastFetch, selectedIndex: selectedIndex, onIndexChanged: (value) => setState(() => selectedIndex = value)),
        TradeEnginePage(
          backendUrl: backendUrl,
          selectedIndex: selectedIndex,
          market: market,
          signals: signals,
          ai: ai,
          tradePlans: tradePlans,
          feed: feed,
          liveStatus: liveTrading,
          lastFetch: lastFetch,
          onIndexChanged: (value) => setState(() => selectedIndex = value),
        ),
        BrokerHomePage(
          backendUrl: backendUrl,
          market: market,
          signals: signals,
          angelOnline: angelOnline,
          status: status,
          onIndexSelected: (value) => setState(() => selectedIndex = value),
        ),
        AiChatPage(backendUrl: backendUrl, selectedIndex: selectedIndex),
        OrderFlowPage(signalBackendUrl: signalBackendUrl),
        Builder(
          builder: (tabContext) => QuantEngineLabPage(
            backendUrl: backendUrl,
            index: selectedIndex,
            market: market,
            lastFetch: lastFetch,
            onOpenBacktest: () => DefaultTabController.of(tabContext).animateTo(tabs.indexOf('Backtesting')),
          ),
        ),
        StrategyLibraryPage(market: market, signals: signals, selectedIndex: selectedIndex),
        FlowMonitorPage(signalBackendUrl: signalBackendUrl),
        const DailyAiMemoryPage(),
        Builder(builder: (tabContext) => SmcChartPage(index: selectedIndex, market: _market(selectedIndex), signal: _signal(selectedIndex), ai: ai, onIndexChanged: (value) => setState(() => selectedIndex = value), onOpenAiChat: () => DefaultTabController.of(tabContext).animateTo(tabs.indexOf('AI Chat')))),
      ]),
    ),
  );
}

IconData _tabIcon(int index) => switch (index) {
  0 => Icons.dashboard_outlined,
  1 => Icons.show_chart,
  2 => Icons.table_chart_outlined,
  3 => Icons.bar_chart,
  4 => Icons.tune,
  5 => Icons.bolt,
  6 => Icons.shield_outlined,
  7 => Icons.public,
  8 => Icons.query_stats,
  9 => Icons.settings_ethernet,
  10 => Icons.psychology_alt_outlined,
  11 => Icons.monitor_heart_outlined,
  12 => Icons.cloud_outlined,
  13 => Icons.menu_book_outlined,
  14 => Icons.account_tree_outlined,
  15 => Icons.auto_awesome_outlined,
  16 => Icons.layers_outlined,
  17 => Icons.account_balance_wallet_outlined,
  18 => Icons.picture_as_pdf_outlined,
  19 => Icons.chat_bubble_outline,
  20 => Icons.show_chart,
  21 => Icons.library_books_outlined,
  22 => Icons.layers_outlined,
  23 => Icons.speed,
  24 => Icons.candlestick_chart,
  _ => Icons.layers_outlined,
};

class DataHealthPage extends StatelessWidget {
  const DataHealthPage({
    required this.backendUrl,
    required this.signalBackendUrl,
    required this.apiOnline,
    required this.signalsOnline,
    required this.angelOnline,
    required this.status,
    required this.diagnostics,
    required this.diagnosticsError,
    required this.market,
    required this.lastFetch,
    required this.onRefresh,
    super.key,
  });
  final String backendUrl;
  final String signalBackendUrl;
  final bool apiOnline, signalsOnline, angelOnline;
  final String status;
  final Map<String, dynamic> diagnostics;
  final String? diagnosticsError;
  final Map<String, dynamic> market;
  final String? lastFetch;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('DATA HEALTH & CONNECTION STATUS', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 10),
      Card(child: Column(children: [
        _healthRow('Backend / Railway API', apiOnline),
        _healthRow('Signals API response', signalsOnline),
        _healthRow('Angel One authenticated session', angelOnline),
        ListTile(leading: const Icon(Icons.link), title: const Text('AI / chat backend'), subtitle: SelectableText(backendUrl)),
        ListTile(leading: const Icon(Icons.show_chart), title: const Text('Live signals backend'), subtitle: SelectableText(signalBackendUrl)),
        ListTile(leading: const Icon(Icons.info_outline), title: const Text('Current service status'), subtitle: Text(status)),
        ListTile(leading: const Icon(Icons.history), title: const Text('Last market snapshot'), subtitle: Text(lastFetch ?? 'No successful market fetch recorded')),
      ])),
      const Section('LIVE SERVICE DIAGNOSTICS'),
      Card(child: Column(children: [
        ListTile(
          leading: const Icon(Icons.dns_outlined),
          title: const Text('Backend worker cycle'),
          subtitle: Text('Age: ${_diagValue(diagnostics, 'backend', 'cycle_age_seconds', fallback: 'unknown')} sec • Fresh: ${_diagValue(diagnostics, 'backend', 'cycle_fresh', fallback: 'unknown')}'),
        ),
        ListTile(
          leading: const Icon(Icons.link),
          title: const Text('Angel One session'),
          subtitle: Text('Authenticated: ${_diagValue(diagnostics, 'angel_one', 'authenticated')} • WebSocket open: ${_diagValue(diagnostics, 'angel_one', 'stream_open')} • Last tick age: ${_diagValue(diagnostics, 'angel_one', 'last_tick_age_seconds')} sec'),
        ),
        ListTile(
          leading: const Icon(Icons.show_chart),
          title: const Text('Market data'),
          subtitle: Text('Instrument master rows: ${_diagValue(diagnostics, 'instrument_master', 'row_count')} • Snapshots: ${_diagValue(diagnostics, 'market_data', 'snapshot_count')} • Fresh: ${_diagValue(diagnostics, 'market_data', 'fresh_snapshot_count')} • Live: ${_diagValue(diagnostics, 'market_data', 'live_snapshot_count')}'),
        ),
        ListTile(
          leading: const Icon(Icons.psychology_outlined),
          title: const Text('AI provider'),
          subtitle: Text('Configured: ${_diagValue(diagnostics, 'ai', 'configured')} • Model: ${_diagValue(diagnostics, 'ai', 'model')} • Error indexes: ${_diagValue(diagnostics, 'ai', 'error_indexes', fallback: 'none')}'),
        ),
        if (_diagValue(diagnostics, 'angel_one', 'last_error', fallback: '') != '')
          ListTile(leading: const Icon(Icons.warning_amber), title: const Text('Angel One error'), subtitle: Text(_diagValue(diagnostics, 'angel_one', 'last_error', fallback: ''))),
        if (_diagValue(diagnostics, 'angel_one', 'stream_error', fallback: '') != '')
          ListTile(leading: const Icon(Icons.warning_amber), title: const Text('WebSocket error'), subtitle: Text(_diagValue(diagnostics, 'angel_one', 'stream_error', fallback: ''))),
        if (_diagValue(diagnostics, 'ai', 'last_error', fallback: '') != '')
          ListTile(leading: const Icon(Icons.warning_amber), title: const Text('AI request error'), subtitle: Text(_diagValue(diagnostics, 'ai', 'last_error', fallback: ''))),
        ListTile(
          leading: const Icon(Icons.speed),
          title: const Text('Signal engine build timing'),
          subtitle: Text('Last build: ${_diagValue(diagnostics, 'signal_build', 'last_duration_ms')} ms • Builds: ${_diagValue(diagnostics, 'signal_build', 'build_count')} • In flight: ${_diagValue(diagnostics, 'signal_build', 'in_flight')}'),
        ),
        ListTile(
          leading: Icon(diagnostics.isNotEmpty ? Icons.check_circle_outline : Icons.info_outline),
          title: const Text('Diagnostics endpoint'),
          subtitle: Text(diagnostics.isNotEmpty ? 'Connected • backend returned a diagnostic payload' : (diagnosticsError ?? 'Detailed diagnostics not received yet')),
        ),
        if ((diagnostics['restore_errors'] as List?)?.isNotEmpty == true)
          ListTile(leading: const Icon(Icons.warning_amber), title: const Text('Settings restore warnings'), subtitle: Text((diagnostics['restore_errors'] as List).join(' • '))),
      ])),
      const Section('Index feed status'),
      for (final index in indexes)
        Builder(builder: (context) {
          final row = Map<String, dynamic>.from(market[index] as Map? ?? const {});
          final hasPrice = row['ltp'] is num && (row['ltp'] as num) > 0;
          final fresh = row['live'] == true;
          return Card(child: ListTile(
            leading: Icon(fresh ? Icons.check_circle : Icons.error_outline, color: fresh ? Colors.greenAccent : Colors.orangeAccent),
            title: Text(index),
            subtitle: Text(
              'Price: ${_val(row['ltp'])} • Age: ${row['age_seconds'] == null ? 'unknown' : '${_val(row['age_seconds'])} sec'} • ${row['feed_mode'] ?? 'NO DATA'}'
              '${(row['signal_error'] ?? row['error']) == null ? '' : '\nSignal pipeline: ${row['signal_error'] ?? row['error']}'}',
            ),
            trailing: Text(fresh ? 'LIVE' : hasPrice ? 'STALE' : 'NO DATA', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 11, color: fresh ? Colors.greenAccent : Colors.orangeAccent)),
          ));
        }),
      FilledButton.icon(onPressed: onRefresh, icon: const Icon(Icons.refresh), label: const Text('Refresh connection and market status')),
      const SizedBox(height: 8),
      const Text('This page shows safe live-service diagnostics. API keys, JWTs, PINs and other credential values are never displayed.', style: TextStyle(color: Colors.white70, fontSize: 12)),
    ],
  );
}

Widget _healthRow(String label, bool good) => ListTile(
  leading: Icon(good ? Icons.check_circle : Icons.error_outline, color: good ? Colors.greenAccent : Colors.orangeAccent),
  title: Text(label),
  trailing: Text(good ? 'CONNECTED' : 'CHECK', style: TextStyle(color: good ? Colors.greenAccent : Colors.orangeAccent, fontWeight: FontWeight.bold)),
);

String _diagValue(
  Map<String, dynamic> root,
  String section,
  String field, {
  String fallback = 'not available',
}) {
  final value = root[section];
  if (value is Map) {
    final fieldValue = value[field];
    if (fieldValue != null) return fieldValue.toString();
  }
  return fallback;
}

class ApiRailwayPage extends StatelessWidget {
  const ApiRailwayPage({super.key});

  static const links = <(String, String, String)>[];

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('ADVANCED API + RAILWAY CONNECTION', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 8),
      const Text('Use the backend service as the secure bridge between this Android app, Angel One SmartAPI and AI providers. Keep broker and AI secrets on the server, not inside the APK.', style: TextStyle(color: Colors.white70)),
      const SizedBox(height: 10),
      Card(child: Column(children: [
        const ListTile(leading: Icon(Icons.security), title: Text('Recommended production flow'), subtitle: Text('Android app → HTTPS Railway API → Angel One REST/WebSocket + AI providers → normalized market store → signal engine')),
        const Divider(height: 1),
        const ListTile(leading: Icon(Icons.health_and_safety), title: Text('Health checks'), subtitle: Text('Expose /health and verify it before debugging market data. Check deployment logs, environment variables, public HTTPS domain, CORS only if browser clients need it, and request timeouts.')),
        const Divider(height: 1),
        const ListTile(leading: Icon(Icons.vpn_key_outlined), title: Text('Secret handling'), subtitle: Text('Store credentials as Railway variables or encrypted server-side settings. Never commit .env files, API keys, Angel password, PIN, or TOTP seed.')),
      ])),
      for (final item in links)
        Card(
          child: ListTile(
            leading: const Icon(Icons.open_in_new, color: Color(0xFF12D6FF)),
            title: Text(item.$1),
            subtitle: Text(item.$3),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _openExternal(context, item.$2),
          ),
        ),
      const Text('Use runtime diagnostics above to verify the actual backend, broker session and data freshness.', style: TextStyle(fontSize: 12, color: Colors.white70)),
    ],
  );
}

class BacktestingPage extends StatefulWidget {
  const BacktestingPage({required this.backendUrl, super.key});
  final String backendUrl;
  @override
  State<BacktestingPage> createState() => _BacktestingPageState();
}

class _BacktestingPageState extends State<BacktestingPage> {
  String _index = 'NIFTY';
  String _interval = 'FIVE_MINUTE';
  DateTime _to = DateTime.now();
  DateTime _clockNow = DateTime.now();
  Timer? _clockTimer;
  late DateTime _from = _to.subtract(const Duration(days: 7));
  final _fast = TextEditingController(text: '8');
  final _slow = TextEditingController(text: '13');
  final _atr = TextEditingController(text: '14');
  final _stopAtr = TextEditingController(text: '1.5');
  final _targetR = TextEditingController(text: '2.0');
  final _slippage = TextEditingController(text: '0.02');
  final _cost = TextEditingController(text: '0.02');
  bool _loading = false;
  String? _error;
  Map<String, dynamic>? _response;

  String _date(DateTime value) => '${value.year.toString().padLeft(4, '0')}-${value.month.toString().padLeft(2, '0')}-${value.day.toString().padLeft(2, '0')}';
  double _number(TextEditingController controller, double fallback) => double.tryParse(controller.text.trim()) ?? fallback;
  int _integer(TextEditingController controller, int fallback) => int.tryParse(controller.text.trim()) ?? fallback;

  @override
  void initState() {
    super.initState();
    _clockTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _clockNow = DateTime.now());
    });
  }

  @override
  void dispose() {
    _clockTimer?.cancel();
    _fast.dispose(); _slow.dispose(); _atr.dispose(); _stopAtr.dispose();
    _targetR.dispose(); _slippage.dispose(); _cost.dispose();
    super.dispose();
  }

  Future<void> _pickDate({required bool start}) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: start ? _from : _to,
      firstDate: DateTime(now.year - 1),
      lastDate: now,
    );
    if (picked == null || !mounted) return;
    setState(() {
      if (start) {
        _from = picked;
        if (_from.isAfter(_to)) _to = _from;
      } else {
        _to = picked;
        if (_to.isBefore(_from)) _from = _to;
      }
      if (_to.difference(_from).inDays > 30) _from = _to.subtract(const Duration(days: 30));
    });
  }

  Future<void> _run() async {
    if (_from.isAfter(_to) || _to.difference(_from).inDays > 30) {
      setState(() => _error = 'Choose a valid date range of 30 days or less.');
      return;
    }
    setState(() { _loading = true; _error = null; _response = null; });
    try {
      final response = await FreshApi(widget.backendUrl).historicalBacktest({
        'index': _index,
        'from_date': _date(_from),
        'to_date': _date(_to),
        'interval': _interval,
        'fast_ema': _integer(_fast, 8),
        'slow_ema': _integer(_slow, 13),
        'atr_period': _integer(_atr, 14),
        'stop_atr': _number(_stopAtr, 1.5),
        'target_r': _number(_targetR, 2.0),
        'max_hold_bars': 30,
        'slippage_r': _number(_slippage, 0.02),
        'transaction_cost_r': _number(_cost, 0.02),
      });
      if (!mounted) return;
      setState(() => _response = response);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _field(String label, TextEditingController controller, {bool decimal = false}) => TextField(
    controller: controller,
    keyboardType: TextInputType.numberWithOptions(decimal: decimal),
    decoration: InputDecoration(labelText: label),
  );

  @override
  Widget build(BuildContext context) {
    final report = Map<String, dynamic>.from((_response?['report'] as Map?) ?? const {});
    final metrics = Map<String, dynamic>.from((report['metrics'] as Map?) ?? const {});
    final trades = (report['trades'] as List?) ?? const <dynamic>[];
    return ListView(padding: const EdgeInsets.all(12), children: [
      const Text('HISTORICAL STRATEGY BACKTEST', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 6),
      const Text('Uses authenticated Angel One historical index candles and replays EMA crossover + ATR stop/target rules. No prefilled or fabricated trade outcomes.', style: TextStyle(color: Colors.white70, fontSize: 12)),
      const SizedBox(height: 8),
      Card(child: Padding(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10), child: Row(children: [
        const Icon(Icons.schedule, color: Color(0xFF12D6FF)),
        const SizedBox(width: 8),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('DEVICE DATE & TIME', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 1)),
          Text('${_date(_clockNow)}  ${_clockNow.hour.toString().padLeft(2, '0')}:${_clockNow.minute.toString().padLeft(2, '0')}:${_clockNow.second.toString().padLeft(2, '0')}', style: const TextStyle(fontWeight: FontWeight.w700)),
          const Text('Historical candles use the exchange session 09:15–15:30 IST; select dates below.', style: TextStyle(fontSize: 11, color: Colors.white70)),
        ])),
      ]))),
      const SizedBox(height: 10),
      Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        DropdownButtonFormField<String>(
          initialValue: _index,
          decoration: const InputDecoration(labelText: 'F&O index'),
          items: indexes.map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
          onChanged: _loading ? null : (v) { if (v != null) setState(() => _index = v); },
        ),
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          initialValue: _interval,
          decoration: const InputDecoration(labelText: 'Historical candle interval'),
          items: const [
            DropdownMenuItem(value: 'ONE_MINUTE', child: Text('1 minute')),
            DropdownMenuItem(value: 'FIVE_MINUTE', child: Text('5 minutes')),
            DropdownMenuItem(value: 'FIFTEEN_MINUTE', child: Text('15 minutes')),
            DropdownMenuItem(value: 'ONE_HOUR', child: Text('1 hour')),
          ],
          onChanged: _loading ? null : (v) { if (v != null) setState(() => _interval = v); },
        ),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: OutlinedButton.icon(onPressed: _loading ? null : () => _pickDate(start: true), icon: const Icon(Icons.calendar_today), label: Text('From ${_date(_from)}'))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton.icon(onPressed: _loading ? null : () => _pickDate(start: false), icon: const Icon(Icons.event), label: Text('To ${_date(_to)}'))),
        ]),
        const SizedBox(height: 10),
        Row(children: [Expanded(child: _field('Fast EMA', _fast)), const SizedBox(width: 8), Expanded(child: _field('Slow EMA', _slow)), const SizedBox(width: 8), Expanded(child: _field('ATR period', _atr))]),
        const SizedBox(height: 10),
        Row(children: [Expanded(child: _field('Stop ATR ×', _stopAtr, decimal: true)), const SizedBox(width: 8), Expanded(child: _field('Target (R)', _targetR, decimal: true))]),
        const SizedBox(height: 10),
        Row(children: [Expanded(child: _field('Slippage (R)', _slippage, decimal: true)), const SizedBox(width: 8), Expanded(child: _field('Costs (R)', _cost, decimal: true))]),
        const SizedBox(height: 12),
        SizedBox(width: double.infinity, child: FilledButton.icon(
          onPressed: _loading ? null : _run,
          icon: _loading ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.play_arrow),
          label: Text(_loading ? 'FETCHING CANDLES & BACKTESTING…' : 'RUN HISTORICAL BACKTEST'),
        )),
      ]))),
      if (_error != null) Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Backtest failed: $_error', style: const TextStyle(color: Colors.orangeAccent)),
              if (_error!.contains('HTTP 404')) ...[
                const SizedBox(height: 8),
                const Text(
                  'The APK requested /v1/backtest/historical, but the server returned 404 (route not found). This route exists in the Fresh-Apk backend source. The deployed service may be running an older image or a different app/root directory. Redeploy the backend from this repository, then confirm /openapi.json lists POST /v1/backtest/historical. This is a server deployment mismatch, not a strategy result.',
                  style: TextStyle(fontSize: 12, color: Colors.white70),
                ),
                const SizedBox(height: 6),
                TextButton.icon(
                  onPressed: () => launchUrl(Uri.parse('https://nse-algo-backend-final-production.up.railway.app/openapi.json'), mode: LaunchMode.externalApplication),
                  icon: const Icon(Icons.open_in_new),
                  label: const Text('Check deployed API routes'),
                ),
              ],
            ],
          ),
        ),
      ),
      if (_response != null) ...[
        Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text((report['status'] ?? 'NO RESULT').toString(), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900)),
          InfoRow('Mode', (report['mode'] ?? '—').toString()),
          InfoRow('Index / interval', '${_response!['index'] ?? _index} / ${_response!['interval'] ?? _interval}'),
          InfoRow('Valid candles', (report['candle_count'] ?? 0).toString()),
          InfoRow('Sample first candle', (report['first_candle'] ?? '—').toString()),
          InfoRow('Sample last candle', (report['last_candle'] ?? '—').toString()),
          const Divider(),
          InfoRow('Closed trades', (metrics['n'] ?? 0).toString()),
          InfoRow('Win rate', metrics['win_rate'] == null ? '—' : '${((metrics['win_rate'] as num) * 100).toStringAsFixed(1)}%'),
          InfoRow('Net expectancy (R/trade)', (metrics['expectancy_r'] ?? '—').toString()),
          InfoRow('Net total (R)', (metrics['net_total_r'] ?? '—').toString()),
          InfoRow('Profit factor', (metrics['profit_factor'] ?? '—').toString()),
          InfoRow('Max drawdown (R)', (metrics['max_drawdown_r'] ?? '—').toString()),
        ]))),
        if (trades.isNotEmpty) ...[
          const Section('Simulated trades'),
          for (final item in trades.reversed.take(30))
            if (item is Map) Card(child: ExpansionTile(
              title: Text('${item['side'] ?? '—'} • R=${item['r'] ?? '—'}'),
              subtitle: Text('${item['entry_time'] ?? '—'} → ${item['exit_time'] ?? '—'} • ${item['exit_reason'] ?? '—'}'),
              children: [
                for (final entry in item.entries) InfoRow(entry.key.toString(), entry.value.toString()),
              ],
            )),
        ],
        const Section('Backtest assumptions & limitations'),
        for (final assumption in (report['assumptions'] as List?) ?? const <dynamic>[])
          Padding(padding: const EdgeInsets.symmetric(vertical: 3), child: Text('• ${assumption.toString()}')),
      ],
    ]);
  }
}

class MarketDiagnosticsPage extends StatelessWidget {
  const MarketDiagnosticsPage({
    required this.market,
    required this.signals,
    required this.feed,
    required this.diagnostics,
    required this.lastFetch,
    super.key,
  });

  final Map<String, dynamic> market, signals, feed, diagnostics;
  final String? lastFetch;

  static const links = <(String, String, String)>[];

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('MARKET DATA DIAGNOSTICS • CURRENT BACKEND SNAPSHOT', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 8),
      Card(child: Column(children: [
        InfoRow('Latest fetch', lastFetch ?? 'No successful fetch recorded'),
        InfoRow('WebSocket stream', feed['stream_open'] == true ? 'OPEN' : 'NOT CONFIRMED OPEN'),
        InfoRow('Ticks received', (feed['tick_count'] ?? 0).toString()),
        InfoRow('Unique tokens seen', (feed['unique_tokens_seen'] ?? diagnostics['unique_tokens'] ?? 0).toString()),
        InfoRow('Store updates', (diagnostics['update_count'] ?? 0).toString()),
        InfoRow('Last feed error', (feed['last_error'] ?? 'None reported').toString()),
      ])),
      const Text('Index data and signal outputs', style: TextStyle(fontWeight: FontWeight.w900)),
      const SizedBox(height: 6),
      for (final index in indexes)
        Builder(builder: (context) {
          final m = Map<String, dynamic>.from(market[index] as Map? ?? const {});
          final sig = Map<String, dynamic>.from(signals[index] as Map? ?? const {});
          final hasPrice = m['ltp'] != null;
          return Card(child: ExpansionTile(
            leading: Icon(hasPrice ? Icons.show_chart : Icons.hourglass_empty, color: hasPrice ? Colors.greenAccent : Colors.orangeAccent),
            title: Text(index),
            subtitle: Text('LTP: ${_val(m['ltp'])} • OI: ${_val(m['oi'])} • Feed: ${(m['feed_mode'] ?? m['last_fetch_label'] ?? 'NO DATA')}'),
            children: [
              InfoRow('Signal decision', (sig['decision'] ?? sig['signal'] ?? 'WAIT / NO DATA').toString()),
              InfoRow('Confidence', sig['confidence'] == null ? '—' : '${sig['confidence']}%'),
              InfoRow('PCR', _val(sig['pcr'] ?? m['pcr'])),
              InfoRow('RSI', _val((sig['indicators'] as Map?)?['rsi'])),
              InfoRow('EMA fast / slow', '${_val((sig['indicators'] as Map?)?['ema_fast'])} / ${_val((sig['indicators'] as Map?)?['ema_slow'])}'),
              InfoRow('Data age', m['age_seconds'] == null ? 'Unknown' : '${_val(m['age_seconds'])} sec'),
              if (sig['reason'] is List)
                Padding(padding: const EdgeInsets.fromLTRB(12, 0, 12, 12), child: Text((sig['reason'] as List).map((e) => '• $e').join('\\n'))),
            ],
          ));
        }),
      const Text('ENGINE MODULES STATUS', style: TextStyle(fontWeight: FontWeight.w900)),
      const SizedBox(height: 6),
      const Text('Operational modules: Angel One SmartAPI/WebSocket, normalized market store, trend/technical indicators, OI classification, strategy ensemble/conflict checks, signal-quality gates, historical backtesting, risk gates and AI/search evidence integration. Status is based on runtime diagnostics, not file presence.', style: TextStyle(color: Colors.white70)),
      const SizedBox(height: 14),
      const Text('Runtime module status is shown above. This page focuses on live diagnostics and working app functions.', style: TextStyle(color: Colors.white70, fontSize: 12)),
    ],
  );
}

class ResearchEnginesPage extends StatelessWidget {
  const ResearchEnginesPage({
    required this.market,
    required this.signals,
    required this.ai,
    required this.commodities,
    required this.optionChains,
    required this.lastFetch,
    required this.selectedIndex,
    required this.onIndexChanged,
    super.key,
  });
  final Map<String, dynamic> market, signals, ai;
  final List<dynamic> commodities;
  final Map<String, List<dynamic>> optionChains;
  final String? lastFetch;
  final String selectedIndex;
  final ValueChanged<String> onIndexChanged;

  @override
  Widget build(BuildContext context) {
    Map<String, dynamic>? commodity;
    for (final raw in commodities) {
      if (raw is! Map) continue;
      final row = Map<String, dynamic>.from(raw);
      final name = (row['name'] ?? row['symbol'] ?? '').toString().toUpperCase();
      if (name == selectedIndex.toUpperCase() ||
          (row['symbol'] ?? '').toString().toUpperCase() == selectedIndex.toUpperCase()) {
        commodity = row;
        break;
      }
    }
    final m = commodity ?? Map<String, dynamic>.from(market[selectedIndex] as Map? ?? const {});
    final s = commodity ?? Map<String, dynamic>.from(signals[selectedIndex] as Map? ?? const {});
    final strategySuite = Map<String, dynamic>.from(
      s['strategy_suite'] as Map? ?? m['strategy_suite'] as Map? ?? const {},
    );
    final strategySignals = Map<String, dynamic>.from(strategySuite['strategies'] as Map? ?? const {});
    final strategyVotes = Map<String, dynamic>.from(strategySuite['votes'] as Map? ?? const {});
    final strategyLevels = Map<String, dynamic>.from(strategySuite['support_resistance'] as Map? ?? const {});
    final indicators = Map<String, dynamic>.from(s['indicators'] as Map? ?? const {});
    final chain = (m['option_chain'] as List?) ?? optionChains[selectedIndex] ?? const <dynamic>[];
    final chainRows = chain.whereType<Map>().map((row) => Map<String, dynamic>.from(row)).toList();
    final callOi = chainRows.where((row) => (row['side'] ?? '').toString().toUpperCase() == 'CE')
        .fold<double>(0, (sum, row) => sum + (row['oi'] is num ? (row['oi'] as num).toDouble() : 0));
    final putOi = chainRows.where((row) => (row['side'] ?? '').toString().toUpperCase() == 'PE')
        .fold<double>(0, (sum, row) => sum + (row['oi'] is num ? (row['oi'] as num).toDouble() : 0));
    final oi = Map<String, dynamic>.from(s['oi_summary'] as Map? ?? const {});
    if (oi.isEmpty && chainRows.isNotEmpty) {
      oi['call_oi'] = callOi;
      oi['put_oi'] = putOi;
      oi['pcr'] = callOi > 0 ? putOi / callOi : null;
      oi['classification'] = callOi <= 0 ? 'DATA REQUIRED' : putOi / callOi >= 1.1 ? 'PUT OI HEAVY' : putOi / callOi <= 0.8 ? 'CALL OI HEAVY' : 'BALANCED';
    }
    final validation = Map<String, dynamic>.from(s['live_validation'] as Map? ?? const {});
    final tf = Map<String, dynamic>.from(s['timeframe_analysis'] as Map? ?? const {});
    final research = Map<String, dynamic>.from(tf['research_pack'] as Map? ?? const {});
    final checks = Map<String, dynamic>.from(research['checks'] as Map? ?? const {});
    final aiRow = Map<String, dynamic>.from(ai[selectedIndex] as Map? ?? const {});
    final fresh = m['live'] == true;

    return ListView(padding: const EdgeInsets.all(12), children: [
      const Text('RESEARCH ENGINES • LIVE BACKEND OUTPUT', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 6),
      const Text('This tab surfaces actual indicator, OI, confluence and validation outputs from available market data.', style: TextStyle(color: Colors.white70, fontSize: 12)),
      const SizedBox(height: 10),
      IndexPicker(selected: selectedIndex, onChanged: onIndexChanged),
      Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(selectedIndex, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900))),
          _statusPill(fresh ? 'LIVE' : 'STALE / NO DATA', fresh ? Colors.greenAccent : Colors.orangeAccent),
        ]),
        Text('Spot LTP ₹${_val(m['ltp'])}', style: const TextStyle(fontSize: 25, fontWeight: FontWeight.w900, color: Color(0xFF12D6FF))),
        Text('Snapshot: ${m['timestamp'] ?? lastFetch ?? 'No snapshot'}', style: const TextStyle(fontSize: 11, color: Colors.white60)),
        Text('Engine trace: source=${m['source'] ?? m['feed_mode'] ?? 'unknown'} • freshness=${fresh ? 'PASS' : 'BLOCKED'} • strategy outputs=${strategySignals.length} • five-layer=${validation['verdict'] ?? 'WAIT / NOT RETURNED'}',
          style: const TextStyle(fontSize: 10, color: Colors.white60)),
        const Divider(height: 22),
        const Text('TECHNICAL INDICATOR ENGINE', style: TextStyle(fontWeight: FontWeight.w900)),
        for (final pair in <(String, dynamic)>[
          ('EMA fast', indicators['ema_fast']), ('EMA slow', indicators['ema_slow']),
          ('SMA 20', indicators['sma20']), ('RSI 14', indicators['rsi14']),
          ('MACD histogram', indicators['macd_hist']), ('ATR 14', indicators['atr14']),
          ('VWAP', indicators['vwap']), ('Bollinger upper', indicators['bb_upper']),
          ('Bollinger mid', indicators['bb_mid']), ('Bollinger lower', indicators['bb_lower']),
          ('Z-score 20', indicators['zscore20']), ('Realized volatility 20', indicators['realized_vol20']),
        ]) InfoRow(pair.$1, _val(pair.$2)),
        const Divider(height: 22),
        const Text('SMC / ORDER-FLOW EVIDENCE', style: TextStyle(fontWeight: FontWeight.w900)),
        InfoRow('BOS', (s['smc'] as Map?)?['bos']?.toString() ?? 'Not supplied'),
        InfoRow('CHoCH', (s['smc'] as Map?)?['choch']?.toString() ?? 'Not supplied'),
        InfoRow('FVG / order block', (s['smc'] as Map?)?['poi']?.toString() ?? 'Run SMC Pro Chart for candle-based analysis'),
        InfoRow('Order-flow depth', (m['depth_status'] ?? m['order_flow_status'] ?? 'Use Order Flow tab; best-five depth is not classified trade prints').toString()),
        const Divider(height: 22),
        const Text('OPTIONS / OPEN INTEREST ENGINE', style: TextStyle(fontWeight: FontWeight.w900)),
        InfoRow('CALL OI', _val(oi['call_oi'])),
        InfoRow('PUT OI', _val(oi['put_oi'])),
        InfoRow('PCR', _val(oi['pcr'])),
        InfoRow('OI regime', (oi['selected_oi_regime'] ?? oi['classification'] ?? 'UNKNOWN').toString()),
        InfoRow('Live option rows', chain.length.toString()),
        if (commodity != null) ...[
          InfoRow('MCX CE quotes', chainRows.where((row) => (row['side'] ?? '').toString().toUpperCase() == 'CE').length.toString()),
          InfoRow('MCX PE quotes', chainRows.where((row) => (row['side'] ?? '').toString().toUpperCase() == 'PE').length.toString()),
          InfoRow('Commodity options gate', 'WAIT'),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 4, vertical: 6),
            child: Text(
              'Commodity CE/PE entries remain blocked until option Greeks, option ATR and risk inputs are verified. No signal is fabricated.',
              style: TextStyle(color: Colors.orangeAccent, fontSize: 11),
            ),
          ),
        ],
        const Divider(height: 22),
        const Text('RESEARCH PACK & CONFLUENCE', style: TextStyle(fontWeight: FontWeight.w900)),
        InfoRow('Candidate alignment', (research['candidate_alignment'] ?? 'UNKNOWN').toString()),
        InfoRow('Evidence alignment score', _val(research['evidence_score'])),
        InfoRow('Known directional checks', (research['known_directional_checks'] ?? 0).toString()),
        for (final entry in checks.entries)
          if (entry.value is Map)
            InfoRow(entry.key.replaceAll('_', ' '), (entry.value as Map)['state']?.toString() ?? 'UNKNOWN'),
        const Divider(height: 22),
        const Text('UNIFIED STRATEGY SUITE', style: TextStyle(fontWeight: FontWeight.w900)),
        InfoRow('Suite status', (strategySuite['status'] ?? 'NOT AVAILABLE').toString()),
        InfoRow('Consensus signal', (strategySuite['signal'] ?? 'WAIT').toString()),
        InfoRow('Market regime', (strategySuite['market_regime'] ?? 'UNKNOWN').toString()),
        InfoRow('Long votes', (strategyVotes['LONG'] ?? '—').toString()),
        InfoRow('Short votes', (strategyVotes['SHORT'] ?? '—').toString()),
        InfoRow('OI build-up context', (strategySuite['oi_context'] ?? 'UNKNOWN').toString()),
        InfoRow('ATR 14', _val(strategySuite['atr_14'])),
        InfoRow('Support (20 bars)', _val(strategyLevels['support'])),
        InfoRow('Resistance (20 bars)', _val(strategyLevels['resistance'])),
        for (final entry in strategySignals.entries)
          InfoRow(entry.key.replaceAll('_', ' ').toUpperCase(), (entry.value ?? 'WAIT').toString()),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          child: Text(
            'Strategy suite is research-only. Missing OI change stays UNKNOWN; the suite cannot override the five-layer risk gate or place orders.',
            style: TextStyle(color: Colors.white70, fontSize: 11),
          ),
        ),
        const Divider(height: 22),
        const Text('SIGNAL & VALIDATION OUTPUT', style: TextStyle(fontWeight: FontWeight.w900)),
        InfoRow('Strategy candidate', (s['decision'] ?? 'NO DATA').toString()),
        InfoRow('Validated decision', (validation['decision'] ?? 'WAIT').toString()),
        InfoRow('Validation verdict', (validation['verdict'] ?? 'NOT VALIDATED').toString()),
        InfoRow('AI action', (aiRow['action'] ?? 'AI NOT READY').toString()),
        InfoRow('Blocked reasons', ((validation['blocks'] as List?) ?? const []).map((x) => x.toString()).join(', ').isEmpty ? 'None reported' : ((validation['blocks'] as List?) ?? const []).map((x) => x.toString()).join(', ')),
      ]))),
      const Section('VALIDATION PERFORMANCE'),
      InfoRow('Index snapshot compute time', '${(s['performance'] as Map?)?['index_snapshot_ms'] ?? '—'} ms'),
      InfoRow('Five-layer validation time', '${(s['performance'] as Map?)?['five_layer_validation_ms'] ?? '—'} ms'),
      InfoRow('Overall signal build time', '${(s['performance'] as Map?)?['signal_build_ms'] ?? '—'} ms'),
      const Text('Timings are measured runtime values. A missing timing means the engine did not return a measurement.', style: TextStyle(fontSize: 11, color: Colors.white70)),
    ]);
  }

  Widget _statusPill(String text, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.12), border: Border.all(color: color.withValues(alpha: 0.4)), borderRadius: BorderRadius.circular(20)),
    child: Text(text, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w900)),
  );
}

class TradingSetupPage extends StatelessWidget {
  const TradingSetupPage({
    required this.backendUrl,
    required this.selectedIndex,
    required this.aiProviders,
    required this.apiOnline,
    required this.signalsOnline,
    required this.angelOnline,
    required this.market,
    required this.signals,
    required this.ai,
    required this.liveStatus,
    required this.lastFetch,
    super.key,
  });
  final String backendUrl;
  final String selectedIndex;
  final Map<String, dynamic> aiProviders;
  final bool apiOnline, signalsOnline, angelOnline;
  final Map<String, dynamic> market, signals, ai, liveStatus;
  final String? lastFetch;

  static const sections = <(String, String, List<(String, String, String)>)>[];

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('COMPLETE TRADING SYSTEM • ANGEL ONE EDITION', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 8),
      Builder(builder: (context) {
        final liveIndexes = market.values.whereType<Map>().where((row) => row['live'] == true).length;
        final optionRows = market.values.whereType<Map>().fold<int>(0, (sum, row) => sum + (((row['option_chain'] as List?) ?? const []).length));
        final indicatorReady = signals.values.whereType<Map>().any((row) => row['indicators'] is Map);
        final validationReady = signals.values.whereType<Map>().any((row) => row['live_validation'] is Map);
        final providerMap = Map<String, dynamic>.from(aiProviders['providers'] as Map? ?? const {});
        final geminiProvider = Map<String, dynamic>.from(providerMap['gemini'] as Map? ?? const {});
        final geminiReady = geminiProvider['ok'] == true;
        final aiReady = ai.values.whereType<Map>().any((row) => row['action'] != null);
        final checks = <(String, bool, String)>[
          ('1. Backend API', apiOnline, backendUrl),
          ('2. Angel One login', angelOnline, 'Authenticated session required'),
          ('3. Live market data', liveIndexes > 0, '$liveIndexes of ${indexes.length} indexes fresh'),
          ('4. Indicators & strategy engine', indicatorReady, 'Deterministic indicators and OI strategy output'),
          ('5. Option chain / OI', optionRows > 0, '$optionRows option quotes in latest snapshots'),
          ('6. Signal risk validation', validationReady, 'Backend supplies explicit fail-closed checks'),
          ('7. Historical backtest', angelOnline, 'Historical candle replay requires an authenticated Angel One session'),
          ('8. Gemini provider connectivity', geminiReady, (geminiProvider['status'] ?? 'Real Gemini test required').toString()),
          ('9. AI signal analysis', aiReady, 'Review is advisory; provider connectivity alone is not a signal decision'),
          ('10. Execution / order status', liveStatus.isNotEmpty, '${liveStatus['mode'] ?? 'Status not returned'} • live orders remain gated by risk and explicit approval'),
        ];
        return Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('LIVE SETUP CHECKLIST • 10 MODULES', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          Text('Last snapshot: ${lastFetch ?? 'No market snapshot'}', style: const TextStyle(fontSize: 11, color: Colors.white60)),
          const Divider(),
          for (final item in checks)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: Icon(item.$2 ? Icons.check_circle : Icons.error_outline, color: item.$2 ? Colors.greenAccent : Colors.orangeAccent),
              title: Text(item.$1, style: const TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(item.$3, maxLines: 2, overflow: TextOverflow.ellipsis),
              trailing: Text(item.$2 ? 'READY' : 'CHECK', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: item.$2 ? Colors.greenAccent : Colors.orangeAccent)),
              onTap: item.$1.startsWith('7.') ? () => DefaultTabController.of(context).animateTo(tabs.indexOf('Backtesting')) : null,
            ),
          SizedBox(width: double.infinity, child: FilledButton.icon(
            onPressed: () => DefaultTabController.of(context).animateTo(tabs.indexOf('Backtesting')),
            icon: const Icon(Icons.query_stats),
            label: const Text('OPEN HISTORICAL BACKTEST'),
          )),
        ])));
      }),
      const SizedBox(height: 8),
      GeminiSignalReview(backendUrl: backendUrl, selectedIndex: selectedIndex),
      const SizedBox(height: 8),
      const Text('Broker choice: Angel One SmartAPI. No Zerodha/Kite integration is required for this app.', style: TextStyle(color: Color(0xFF12D6FF), fontWeight: FontWeight.w700)),
      const SizedBox(height: 12),
      Card(child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
          Text('SYSTEM FLOW', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
          SizedBox(height: 8),
          Text('Angel One REST + WebSocket → freshness/data-quality gate → normalized market store → indicators + OI/option-chain engine → AI/search evidence → signal scoring → historical backtest validation → risk limits → optional explicitly gated Angel One order → order/fill/position monitor → dashboard + alerts'),
          SizedBox(height: 8),
          Text('Fail-safe: stale or incomplete feed, unknown lot size, wide spread, strategy conflict, exceeded risk limits or broker errors should block a trade and show WAIT/NO TRADE.', style: TextStyle(color: Colors.orangeAccent)),
        ]),
      )),
      const SizedBox(height: 8),
      for (final section in sections)
        Card(
          child: ExpansionTile(
            initiallyExpanded: false,
            leading: const Icon(Icons.account_tree_outlined, color: Color(0xFF12D6FF)),
            title: Text(section.$1, style: const TextStyle(fontWeight: FontWeight.w800)),
            subtitle: Text(section.$2, maxLines: 3, overflow: TextOverflow.ellipsis),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                child: Text(section.$2),
              ),
              for (final link in section.$3)
                ListTile(
                  dense: true,
                  leading: const Icon(Icons.open_in_new, size: 18),
                  title: Text(link.$1),
                  subtitle: Text(link.$3),
                  onTap: () => _openExternal(context, link.$2),
                ),
            ],
          ),
        ),
      const Card(child: Padding(
        padding: EdgeInsets.all(12),
        child: Text('Decision support only. Validate fresh broker timestamps, provider output and deterministic risk gates before considering any trade; no signal guarantees profit.', style: TextStyle(fontSize: 12, color: Colors.white70)),
      )),
    ],
  );
}

Future<void> _openExternal(BuildContext context, String url) async {
  final uri = Uri.parse(url);
  final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
  if (!opened && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open link. Please check your browser.')));
  }
}

class DashboardPage extends StatelessWidget {
  const DashboardPage({required this.index,required this.connected,required this.status,required this.signals,required this.market,required this.aiProviders,required this.tradePlans,required this.qualifiedCount,required this.lastFetch,required this.onSelected,super.key});
  final String index; final bool connected; final String status;
  final Map<String,dynamic> signals,market,aiProviders; final List<dynamic> tradePlans; final int qualifiedCount; final String? lastFetch; final ValueChanged<String> onSelected;
  bool _has(dynamic v)=>v!=null&&v.toString().trim().isNotEmpty;
  double _n(dynamic v)=>v is num?v.toDouble():double.tryParse(v?.toString()??'')??0;
  @override Widget build(BuildContext context){
    final s=Map<String,dynamic>.from(signals[index] as Map? ?? const{}),m=Map<String,dynamic>.from(market[index] as Map? ?? const{});
    final f=Map<String,dynamic>.from(s['order_flow'] as Map? ?? m['order_flow'] as Map? ?? const{}),i=Map<String,dynamic>.from(s['indicators'] as Map? ?? const{}),v=Map<String,dynamic>.from(s['live_validation'] as Map? ?? const{}),g=(s['guards'] as List? ?? const[]);
    final providers=Map<String,dynamic>.from(aiProviders['providers'] as Map? ?? const{});
    final gemini=Map<String,dynamic>.from(providers['gemini'] as Map? ?? const{});
    final openrouter=Map<String,dynamic>.from(providers['openrouter'] as Map? ?? const{});
    final d=(s['decision']??'WAIT').toString().toUpperCase(),fresh=s['data_fresh']==true&&connected,buy=_n(f['buy_volume']),sell=_n(f['sell_volume']),total=buy+sell;
    final layers=<List<dynamic>>[
      ['Market data integrity','Angel One quote + freshness',_has(m['ltp'])&&fresh],
      ['Trend structure','EMA alignment',_has(i['ema_fast'])&&_has(i['ema_slow'])],
      ['Momentum','RSI evidence',_has(i['rsi'])],
      ['Volatility','ATR evidence',_has(i['atr14'])],
      ['Market regime','Trend / range state',_has(s['regime'])],
      ['Order flow','Buy/sell volume evidence',f.isNotEmpty],
      ['Options analytics','Strike and side',_has(s['strike'])&&_has(s['option_side'])],
      ['Strategy consensus','Backend decision',_has(s['decision'])],
      ['Quant scoring','Quant evidence',_n(s['quant_score']) > 0 || _has(s['quant'])],
      ['Risk management','Entry, stop, target',_has(s['entry'])&&_has(s['stop_loss'])&&_has(s['target'])&&g.isEmpty],
    ];
    final stable=Map<String,dynamic>.from(s['signal_stability'] as Map? ?? const{})['state']=='CONFIRMED';
    final gates=<List<dynamic>>[
      ['Freshness gate','Fresh broker data',fresh],['Live validation','Backend verdict PASS',v['verdict']=='PASS'],
      ['Strategy agreement','Actionable candidate',d=='CALL BUY'||d=='PUT BUY'],
      ['Risk gate','No blockers; stop and target',g.isEmpty&&_has(s['stop_loss'])&&_has(s['target'])],
      ['Final decision gate','Stable confirmed trade plan',stable&&tradePlans.any((p)=>p is Map&&(p['index']??'').toString().toUpperCase()==index.toUpperCase())],
    ];
    final c=d=='CALL BUY'?const Color(0xFF35D39A):d=='PUT BUY'?const Color(0xFFFF6577):const Color(0xFFF5B84B);
    return ListView(padding:const EdgeInsets.fromLTRB(14,12,14,28),children:[
      const Text('AI TRADING TERMINAL',style:TextStyle(fontSize:11,letterSpacing:2,color:Color(0xFF6DDBFF),fontWeight:FontWeight.w900)),
      const SizedBox(height:4),const Text('Market command center',style:TextStyle(fontSize:25,fontWeight:FontWeight.w900)),
      const SizedBox(height:14),
      Container(padding:const EdgeInsets.all(16),decoration:BoxDecoration(gradient:const LinearGradient(colors:[Color(0xFF142536),Color(0xFF101722)]),borderRadius:BorderRadius.circular(20),border:Border.all(color:const Color(0xFF294052))),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        Row(children:[Expanded(child:DropdownButtonFormField<String>(value:index,decoration:const InputDecoration(labelText:'Market',border:InputBorder.none),items:indexes.map((x)=>DropdownMenuItem(value:x,child:Text(x))).toList(),onChanged:(x){if(x!=null)onSelected(x);})),Container(padding:const EdgeInsets.all(8),decoration:BoxDecoration(color:c.withOpacity(.12),borderRadius:BorderRadius.circular(8)),child:Text(d,style:TextStyle(color:c,fontWeight:FontWeight.w900,fontSize:11)))]),
        Text('₹ '+(_has(m['ltp'])?_n(m['ltp']).toStringAsFixed(2):'—'),style:const TextStyle(fontSize:34,fontWeight:FontWeight.w900)),
        const SizedBox(height:12),Row(children:[Expanded(child:_metric('CONFIDENCE',s['confidence']==null?'—':s['confidence'].toString()+'%')),Expanded(child:_metric('REGIME',(s['regime']??'—').toString())),Expanded(child:_metric('QUALIFIED',qualifiedCount.toString()+' / 5'))]),
      ])),
      const SizedBox(height:10),_status('Market feed',fresh?'LIVE VERIFIED':'NOT VERIFIED',fresh),
      const Section('AI PROVIDERS • GEMINI + OPENROUTER'),
      Card(child: Column(children: [
        ListTile(leading: Icon(Icons.circle, color: gemini['ok'] == true ? Colors.greenAccent : Colors.redAccent, size: 12), title: const Text('Gemini'), subtitle: Text((gemini['status'] ?? 'STATUS NOT CHECKED').toString()), trailing: Text((gemini['model'] ?? '—').toString(), style: const TextStyle(fontSize: 10))),
        ListTile(leading: Icon(Icons.circle, color: openrouter['ok'] == true ? Colors.greenAccent : Colors.redAccent, size: 12), title: const Text('OpenRouter'), subtitle: Text((openrouter['status'] ?? 'STATUS NOT CHECKED').toString()), trailing: Text((openrouter['model'] ?? '—').toString(), style: const TextStyle(fontSize: 10))),
      ])),
      const SizedBox(height:18),const Text('ORDER FLOW',style:TextStyle(fontSize:15,fontWeight:FontWeight.w900,letterSpacing:1)),
      const SizedBox(height:8),Container(padding:const EdgeInsets.all(14),decoration:BoxDecoration(color:const Color(0xFF101722),borderRadius:BorderRadius.circular(16),border:Border.all(color:const Color(0xFF202D3A))),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        Row(children:[Expanded(child:_metric('BUY VOLUME',f.isEmpty?'—':_fmt(buy),const Color(0xFF35D39A))),Expanded(child:_metric('SELL VOLUME',f.isEmpty?'—':_fmt(sell),const Color(0xFFFF6577))),Expanded(child:_metric('DELTA',f.isEmpty?'—':_fmt(buy-sell),(buy-sell)>=0?const Color(0xFF35D39A):const Color(0xFFFF6577)))]),
        const SizedBox(height:14),if(total>0)ClipRRect(borderRadius:BorderRadius.circular(6),child:SizedBox(height:12,child:Row(children:[Expanded(flex:(buy/total*1000).round().clamp(1,1000),child:Container(color:const Color(0xFF35D39A))),Expanded(flex:(sell/total*1000).round().clamp(1,1000),child:Container(color:const Color(0xFFFF6577)))])))else Container(height:12,color:const Color(0xFF202D3A)),
        const SizedBox(height:8),Text(f.isEmpty?'Order-flow unavailable. Waiting for broker evidence; no synthetic live chart is shown.':'Volume split is indicative and is not guaranteed exchange aggressor-side data.',style:const TextStyle(fontSize:11,color:Colors.white60)),
      ])),
      const SizedBox(height:18),Row(children:[const Expanded(child:Text('10-LAYER TRADING ENGINE',style:TextStyle(fontSize:14,fontWeight:FontWeight.w900))),Text(layers.where((x)=>x[2]==true).length.toString()+'/10 READY',style:const TextStyle(color:Color(0xFF6DDBFF),fontWeight:FontWeight.w800))]),
      const SizedBox(height:8),...layers.asMap().entries.map((e)=>_layer(e.key+1,e.value[0].toString(),e.value[1].toString(),e.value[2]==true)),
      const SizedBox(height:18),Row(children:[const Expanded(child:Text('5-LAYER FINAL VALIDATION',style:TextStyle(fontSize:14,fontWeight:FontWeight.w900))),Text(gates.where((x)=>x[2]==true).length.toString()+'/5 PASS',style:const TextStyle(color:Color(0xFFF5B84B),fontWeight:FontWeight.w800))]),
      const SizedBox(height:8),...gates.asMap().entries.map((e)=>_layer(e.key+1,e.value[0].toString(),e.value[1].toString(),e.value[2]==true)),
      const SizedBox(height:12),Container(padding:const EdgeInsets.all(12),decoration:BoxDecoration(color:const Color(0xFF171B22),borderRadius:BorderRadius.circular(12),border:Border.all(color:const Color(0xFF4B3C20))),child:Text(gates.every((x)=>x[2]==true)?'Validation gates passed for this candidate; verify broker data before trading.':'FINAL DECISION: WAIT. Missing or unverified evidence blocks an actionable signal. Readiness badges reflect received backend fields, not proof that every independent engine is implemented.',style:const TextStyle(fontSize:12,height:1.4))),
      const SizedBox(height:18),const Text('BEST QUALIFIED CANDIDATES',style:TextStyle(fontSize:14,fontWeight:FontWeight.w900)),
      if(tradePlans.isEmpty)const Padding(padding:EdgeInsets.symmetric(vertical:12),child:Text('No trade plan passed all gates. WAIT is the safe default.',style:TextStyle(color:Colors.white60)))else ...tradePlans.take(5).toList().asMap().entries.map((e)=>TradePlanCard(rank:e.key+1,plan:Map<String,dynamic>.from(e.value as Map))),
      if(lastFetch!=null)Padding(padding:const EdgeInsets.only(top:12),child:Text('Last fetch: '+lastFetch!,style:const TextStyle(fontSize:10,color:Colors.white38))),
    ]);
  }
  Widget _metric(String a,String b,[Color c=const Color(0xFFE7EEF7)])=>Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(a,style:const TextStyle(fontSize:9,letterSpacing:.7,color:Colors.white54,fontWeight:FontWeight.w800)),const SizedBox(height:4),Text(b,maxLines:1,overflow:TextOverflow.ellipsis,style:TextStyle(fontSize:13,fontWeight:FontWeight.w900,color:c))]);
  Widget _status(String a,String b,bool ok)=>Container(padding:const EdgeInsets.all(12),decoration:BoxDecoration(color:const Color(0xFF101722),borderRadius:BorderRadius.circular(12),border:Border.all(color:const Color(0xFF202D3A))),child:Row(children:[Icon(Icons.circle,size:9,color:ok?const Color(0xFF35D39A):const Color(0xFFFF6577)),const SizedBox(width:9),Text(a,style:const TextStyle(fontWeight:FontWeight.w800)),const Spacer(),Flexible(child:Text(b,textAlign:TextAlign.end,style:TextStyle(fontSize:10,color:ok?const Color(0xFF35D39A):const Color(0xFFFF6577),fontWeight:FontWeight.w800)))]));
  Widget _layer(int n,String a,String b,bool ok)=>Container(margin:const EdgeInsets.only(bottom:6),padding:const EdgeInsets.symmetric(horizontal:11,vertical:10),decoration:BoxDecoration(color:const Color(0xFF101722),borderRadius:BorderRadius.circular(11),border:Border.all(color:const Color(0xFF202D3A))),child:Row(children:[Container(width:28,height:28,alignment:Alignment.center,decoration:BoxDecoration(color:(ok?const Color(0xFF35D39A):const Color(0xFFFF6577)).withOpacity(.12),borderRadius:BorderRadius.circular(8)),child:Text(n.toString().padLeft(2,'0'),style:TextStyle(fontSize:10,fontWeight:FontWeight.w900,color:ok?const Color(0xFF35D39A):const Color(0xFFFF6577)))),const SizedBox(width:10),Expanded(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(a,style:const TextStyle(fontSize:12,fontWeight:FontWeight.w800)),Text(b,style:const TextStyle(fontSize:10,color:Colors.white54))])),Icon(ok?Icons.check_circle:Icons.lock_outline,size:17,color:ok?const Color(0xFF35D39A):const Color(0xFFFF6577))]));
  String _fmt(double n)=>n.abs()>=10000000?(n/10000000).toStringAsFixed(2)+'Cr':n.abs()>=100000?(n/100000).toStringAsFixed(2)+'L':n.abs()>=1000?(n/1000).toStringAsFixed(1)+'k':n.toStringAsFixed(0);
}

class MarketPage extends StatelessWidget {
  const MarketPage({required this.selected,required this.onChanged,required this.signal,required this.market,super.key});
  final String selected; final ValueChanged<String> onChanged; final Map<String,dynamic> signal,market;
  @override Widget build(BuildContext context)=>ListView(padding:const EdgeInsets.all(10),children:[
    IndexPicker(selected:selected,onChanged:onChanged),
    const Section('INDIAN INDEX • MARKET PULSE'),
    Card(child:Padding(padding:const EdgeInsets.all(14),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
      Row(children:[Expanded(child:Text(selected,style:const TextStyle(fontSize:23,fontWeight:FontWeight.w900))),Container(padding:const EdgeInsets.symmetric(horizontal:10,vertical:5),decoration:BoxDecoration(color:Colors.cyan.withOpacity(.12),borderRadius:BorderRadius.circular(20)),child:const Text('F&O',style:TextStyle(color:Colors.cyan,fontWeight:FontWeight.w800)))]),
      const SizedBox(height:8),Text('₹ ${_val(market['ltp'])}',style:const TextStyle(fontSize:28,fontWeight:FontWeight.w900)),
      const SizedBox(height:8),Row(children:[Expanded(child:Text('REGIME  ${signal['regime']??'—'}',style:const TextStyle(fontSize:11))),Expanded(child:Text('SIGNAL  ${signal['decision']??'NO DATA'}',style:const TextStyle(fontSize:11,fontWeight:FontWeight.w800)))]),
    ]))),
    ProCandlestickChart(index:selected,market:market,signal:signal),
    const Section('Market Pulse • Indicators'),
    InfoRow('Underlying LTP',_val(market['ltp'])),
    InfoRow('VWAP',_val((signal['indicators'] as Map?)?['vwap'])),
    InfoRow('ATR(14)',_val((signal['indicators'] as Map?)?['atr14'])),
    InfoRow('Decision',signal['decision']?.toString()??'NO DATA'),
    InfoRow('Last fetch',market['timestamp']?.toString()??'—'),
    if (market['signal_error'] != null) InfoRow('Signal pipeline status', market['signal_error'].toString()),
    const Section('Timeframe Data • broker candles only'),
    ...['15m','5m','1m'].map((tf){final arr=((market['timeframes'] as Map?)?[tf] as List?)??const[];final last=arr.isEmpty?null:Map<String,dynamic>.from(arr.last as Map);return Card(child:ListTile(title:Text(tf+' • '+arr.length.toString()+' bars'),subtitle:Text('O '+_val(last?['open'])+' H '+_val(last?['high'])+' L '+_val(last?['low'])+' C '+_val(last?['close'])+' • '+_val(last?['count'])+' ticks')));}),
  ]);
}

class ChainPage extends StatefulWidget {
  const ChainPage({required this.selected, required this.onChanged, required this.market, required this.error, super.key});
  final String selected;
  final ValueChanged<String> onChanged;
  final Map<String, dynamic> market;
  final String? error;
  @override
  State<ChainPage> createState() => _ChainPageState();
}

class _ChainPageState extends State<ChainPage> {
  String _side = 'BOTH';
  String _sort = 'STRIKE';

  double _n(dynamic value) => value is num ? value.toDouble() : double.tryParse(value?.toString() ?? '') ?? 0;
  String _fmt(dynamic value) => value == null ? '—' : _n(value).toStringAsFixed(_n(value).abs() >= 100 ? 0 : 2);
  String _percent(dynamic value) => value == null ? '—' : '${(_n(value) * 100).toStringAsFixed(2)}%';
  String _flow(Map<String, dynamic> row) {
    if (row['premium_change'] == null || row['oi_change'] == null) return 'UNKNOWN';
    final premium = _n(row['premium_change']);
    final oiChange = _n(row['oi_change']);
    if (premium == 0 || oiChange == 0) return 'FLAT / MIXED';
    if (premium > 0 && oiChange > 0) return 'LONG BUILDUP';
    if (premium < 0 && oiChange > 0) return 'SHORT BUILDUP';
    if (premium > 0 && oiChange < 0) return 'SHORT COVER';
    return 'LONG UNWIND';
  }

  @override
  Widget build(BuildContext context) {
    final rows = ((widget.market['option_chain'] as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map((raw) => Map<String, dynamic>.from(raw))
        .where((row) => _n(row['strike']) > 0)
        .toList();
    rows.sort((a, b) {
      if (_sort == 'OI') return _n(b['oi']).compareTo(_n(a['oi']));
      if (_sort == 'VOLUME') return _n(b['volume']).compareTo(_n(a['volume']));
      return _n(a['strike']).compareTo(_n(b['strike']));
    });
    final spot = _n(widget.market['ltp']);
    final strikes = rows.map((row) => _n(row['strike'])).toSet().toList()..sort();
    final atm = strikes.isEmpty || spot <= 0 ? null : strikes.reduce((a, b) => (a - spot).abs() <= (b - spot).abs() ? a : b);
    final callRows = rows.where((r) => (r['side'] ?? '').toString().toUpperCase() == 'CE').toList();
    final putRows = rows.where((r) => (r['side'] ?? '').toString().toUpperCase() == 'PE').toList();
    final callOi = callRows.fold<double>(0, (sum, r) => sum + _n(r['oi']));
    final putOi = putRows.fold<double>(0, (sum, r) => sum + _n(r['oi']));
    final callWall = callRows.isEmpty ? null : callRows.reduce((a, b) => _n(a['oi']) >= _n(b['oi']) ? a : b);
    final putWall = putRows.isEmpty ? null : putRows.reduce((a, b) => _n(a['oi']) >= _n(b['oi']) ? a : b);
    final pcr = callOi > 0 ? putOi / callOi : null;
    final filtered = rows.where((r) => _side == 'BOTH' || (r['side'] ?? '').toString().toUpperCase() == _side).toList();

    return ListView(padding: const EdgeInsets.all(10), children: [
      IndexPicker(selected: widget.selected, onChanged: widget.onChanged),
      const SizedBox(height: 6),
      const Text('PRO OPTION CHAIN', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 4),
      Text('Spot ₹${_fmt(widget.market['ltp'])} • ${widget.market['feed_mode'] ?? 'NO DATA'} • ${rows.length} available option quotes', style: const TextStyle(color: Colors.white70, fontSize: 12)),
      const SizedBox(height: 8),
      Card(child: Padding(padding: const EdgeInsets.all(12), child: Row(children: [
        Expanded(child: _summary('CALL OI', callOi, Colors.redAccent)),
        Expanded(child: _summary('PUT OI', putOi, Colors.greenAccent)),
        Expanded(child: _summary('PCR', pcr, const Color(0xFF12D6FF))),
      ]))),
      Card(child: Padding(padding: const EdgeInsets.all(12), child: Row(children: [
        Expanded(child: _summary('CALL OI WALL', callWall?['strike'], Colors.redAccent)),
        Expanded(child: _summary('PUT OI WALL', putWall?['strike'], Colors.greenAccent)),
      ]))),
      Row(children: [
        const Text('Side', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(width: 8),
        for (final side in const ['BOTH', 'CE', 'PE'])
          Padding(padding: const EdgeInsets.only(right: 6), child: ChoiceChip(
            label: Text(side == 'BOTH' ? 'CALL + PUT' : side),
            selected: _side == side,
            onSelected: (selected) { if (selected) setState(() => _side = side); },
          )),
      ]),
      Row(children: [
        const Text('Sort by', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(width: 10),
        Expanded(child: DropdownButtonFormField<String>(
          initialValue: _sort,
          decoration: const InputDecoration(isDense: true, contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8)),
          items: const [
            DropdownMenuItem(value: 'STRIKE', child: Text('Strike price')),
            DropdownMenuItem(value: 'OI', child: Text('Open interest')),
            DropdownMenuItem(value: 'VOLUME', child: Text('Volume')),
          ],
          onChanged: (v) { if (v != null) setState(() => _sort = v); },
        )),
      ]),
      if (rows.isEmpty && widget.error != null)
        Card(child: Padding(padding: const EdgeInsets.all(12), child: Text('Option-chain request: ${widget.error}', style: const TextStyle(color: Colors.orangeAccent, fontSize: 12)))),
      if (rows.isEmpty)
        const StatusCard(text: 'No option-chain quotes are available yet. Connect Angel One, sync the instrument master, and wait for live or historical quotes.', good: false)
      else
        Card(child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columnSpacing: 15,
            headingRowHeight: 44,
            dataRowMinHeight: 48,
            dataRowMaxHeight: 68,
            columns: const [
              DataColumn(label: Text('STRIKE')),
              DataColumn(label: Text('SIDE')),
              DataColumn(label: Text('LTP ₹')),
              DataColumn(label: Text('OI')),
              DataColumn(label: Text('OI Δ')),
              DataColumn(label: Text('FLOW')),
              DataColumn(label: Text('PREM Δ')),
              DataColumn(label: Text('VOLUME')),
              DataColumn(label: Text('BID / ASK')),
              DataColumn(label: Text('SPREAD %')),
              DataColumn(label: Text('IV')),
              DataColumn(label: Text('DELTA')),
              DataColumn(label: Text('GAMMA')),
              DataColumn(label: Text('THETA')),
              DataColumn(label: Text('VEGA')),
              DataColumn(label: Text('EXPIRY')),
              DataColumn(label: Text('AGE')),
            ],
            rows: filtered.map((row) {
              final side = (row['side'] ?? '—').toString().toUpperCase();
              final strike = _n(row['strike']);
              final isAtm = atm != null && strike == atm;
              final age = row['age_seconds'];
              final live = row['live'] == true;
              final bid = _n(row['bid']);
              final ask = _n(row['ask']);
              final hasSpread = row['bid'] != null && row['ask'] != null && bid > 0 && ask >= bid && (bid + ask) > 0;
              final spreadPct = hasSpread ? '${((ask - bid) / ((ask + bid) / 2) * 100).toStringAsFixed(2)}%' : '—';
              return DataRow(cells: [
                DataCell(Row(mainAxisSize: MainAxisSize.min, children: [
                  Text(_fmt(strike), style: TextStyle(fontWeight: isAtm ? FontWeight.w900 : FontWeight.w500, color: isAtm ? const Color(0xFF12D6FF) : null)),
                  if (isAtm) const Padding(padding: EdgeInsets.only(left: 4), child: Text('ATM', style: TextStyle(fontSize: 9, color: Color(0xFF12D6FF)))),
                ])),
                DataCell(Text(side, style: TextStyle(fontWeight: FontWeight.w900, color: side == 'CE' ? Colors.redAccent : Colors.greenAccent))),
                DataCell(Text(_fmt(row['ltp']))),
                DataCell(Text(_fmt(row['oi']))),
                DataCell(Text(_fmt(row['oi_change']), style: TextStyle(color: _n(row['oi_change']) >= 0 ? Colors.greenAccent : Colors.redAccent))),
                DataCell(Text(_flow(row), style: const TextStyle(fontSize: 10))),
                DataCell(Text(_percent(row['premium_change']))),
                DataCell(Text(_fmt(row['volume']))),
                DataCell(Text('${_fmt(row['bid'])} / ${_fmt(row['ask'])}')),
                DataCell(Text(spreadPct)),
                DataCell(Text(_fmt(row['iv']))),
                DataCell(Text(_fmt(row['delta']))),
                DataCell(Text(_fmt(row['gamma']))),
                DataCell(Text(_fmt(row['theta']))),
                DataCell(Text(_fmt(row['vega']))),
                DataCell(Text((row['expiry'] ?? '—').toString())),
                DataCell(Text(age == null ? '—' : '${_fmt(age)}s', style: TextStyle(color: live ? Colors.greenAccent : Colors.orangeAccent))),
              ]);
            }).toList(),
          ),
        )),
      const SizedBox(height: 10),
      const Text('OI and Greeks are displayed only when returned by the broker feed. Missing fields remain —; no IV, delta, bid/ask, or volume values are inferred. The ATM marker is based on the closest returned strike to the current spot.', style: TextStyle(fontSize: 11, color: Colors.white70)),
    ]);
  }

  Widget _summary(String label, dynamic value, Color color) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(label, style: const TextStyle(fontSize: 10, color: Colors.white60)),
    const SizedBox(height: 5),
    Text(value == null ? '—' : _fmt(value), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: color)),
  ]);
}


class OIPage extends StatelessWidget {
  const OIPage({required this.signals, required this.market, required this.commodities, required this.optionChains, super.key});
  final Map<String, dynamic> signals;
  final Map<String, dynamic> market;
  final List<dynamic> commodities;
  final Map<String, List<dynamic>> optionChains;
  double _n(dynamic value) => value is num ? value.toDouble() : double.tryParse(value?.toString() ?? '') ?? 0;
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(10), children: [
    const Section('OI Lab — broker option-chain data'),
    const Text('OI/PCR are calculated only from returned Angel One option quotes. Missing chains remain unavailable; no sample OI is generated.', style: TextStyle(fontSize: 11, color: Colors.white70)),
    const Section('MCX LIVE FUTURES • ANGEL ONE'),
    ...commodities.whereType<Map>().map((raw) => Map<String, dynamic>.from(raw)).map((row) {
      final name = (row['name'] ?? row['symbol'] ?? 'MCX').toString().toUpperCase();
      final ltp = row['ltp'] ?? row['last_price'] ?? row['close'];
      final age = row['age_seconds'] ?? row['tick_age_seconds'];
      final live = row['live'] == true && age is num && age >= 0 && age <= 60;
      return Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Expanded(child: Text(name, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16))), Text(live ? 'LIVE' : 'NOT VERIFIED', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: live ? Colors.greenAccent : Colors.orangeAccent))]),
        InfoRow('Contract', (row['symbol'] ?? name).toString()),
        InfoRow('Futures LTP', _val(ltp)),
        InfoRow('Source', (row['source'] ?? row['feed_mode'] ?? 'unknown').toString()),
        InfoRow('Tick age (sec)', age?.toString() ?? 'unknown'),
        InfoRow('Volume', _val(row['volume'])),
        InfoRow('Open interest', _val(row['oi'])),
        if (row['signal_error'] != null || row['error'] != null)
          Text('Feed reason: ${row['signal_error'] ?? row['error']}', style: const TextStyle(color: Colors.orangeAccent, fontSize: 11)),
        const Text('MCX futures data is shown separately. CE/PE option-chain OI is not inferred from futures quotes.', style: TextStyle(color: Colors.white60, fontSize: 10)),
      ])));
    }),
    ...optionUnderlyings.where((index) => indexes.contains(index)).map((index) {
      final signal = Map<String, dynamic>.from(signals[index] as Map? ?? const {});
      final marketRow = Map<String, dynamic>.from(market[index] as Map? ?? const {});
      final cached = optionChains[index];
      final rows = ((marketRow['option_chain'] as List?) ?? cached ?? const <dynamic>[])
          .whereType<Map>().map((row) => Map<String, dynamic>.from(row)).toList();
      final calls = rows.where((row) => (row['side'] ?? row['option_type'] ?? '').toString().toUpperCase().contains('C')).toList();
      final puts = rows.where((row) => (row['side'] ?? row['option_type'] ?? '').toString().toUpperCase().contains('P')).toList();
      final callOi = calls.fold<double>(0, (sum, row) => sum + _n(row['oi']));
      final putOi = puts.fold<double>(0, (sum, row) => sum + _n(row['oi']));
      final callWall = calls.isEmpty ? null : calls.reduce((a, b) => _n(a['oi']) >= _n(b['oi']) ? a : b);
      final putWall = puts.isEmpty ? null : puts.reduce((a, b) => _n(a['oi']) >= _n(b['oi']) ? a : b);
      final old = Map<String, dynamic>.from(signal['oi_summary'] as Map? ?? const {});
      final hasChainOi = rows.any((row) => row['oi'] != null);
      final effectiveCallOi = hasChainOi ? callOi : old['call_oi'];
      final effectivePutOi = hasChainOi ? putOi : old['put_oi'];
      final pcr = hasChainOi ? (callOi > 0 ? putOi / callOi : null) : old['pcr'];
      final classification = pcr is num ? (pcr >= 1.1 ? 'PUT OI HEAVY' : pcr <= 0.8 ? 'CALL OI HEAVY' : 'BALANCED') : 'DATA REQUIRED';
      return Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Expanded(child: Text(index, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w900))), Text(rows.isEmpty ? 'NO CHAIN' : '${rows.length} QUOTES', style: const TextStyle(color: Colors.white60, fontSize: 11))]),
        InfoRow('CALL OI', _val(effectiveCallOi)),
        InfoRow('PUT OI', _val(effectivePutOi)),
        InfoRow('PCR', _val(pcr)),
        InfoRow('CALL OI wall', callWall == null ? '—' : '${callWall['strike'] ?? '—'}'),
        InfoRow('PUT OI wall', putWall == null ? '—' : '${putWall['strike'] ?? '—'}'),
        InfoRow('Classification', hasChainOi ? classification : (old['classification']?.toString() ?? 'WAIT — no broker OI')),
        InfoRow('Selected OI regime', old['selected_oi_regime']?.toString() ?? 'Derived from available chain only'),
        if (marketRow['signal_error'] != null) Text('Signal engine: ${marketRow['signal_error']}', style: const TextStyle(color: Colors.orangeAccent, fontSize: 11)),
      ])));
    }),
  ]);
}

class IndicatorsPage extends StatefulWidget {
  const IndicatorsPage({required this.selected,required this.signal,required this.fast,required this.slow,required this.onChanged,required this.onIndex,super.key});
  final String selected; final Map<String,dynamic> signal; final int fast,slow; final void Function(int,int) onChanged; final ValueChanged<String> onIndex;
  @override State<IndicatorsPage> createState()=>_IndicatorsState();
}
class _IndicatorsState extends State<IndicatorsPage>{
  late TextEditingController fast,slow;
  @override void initState(){super.initState();fast=TextEditingController(text:'8');slow=TextEditingController(text:'13');}
  @override void didUpdateWidget(covariant IndicatorsPage old){super.didUpdateWidget(old);fast.text=widget.fast.toString();slow.text=widget.slow.toString();}
  @override void dispose(){fast.dispose();slow.dispose();super.dispose();}
  @override Widget build(BuildContext context){final i=Map<String,dynamic>.from(widget.signal['indicators'] as Map? ?? const{});return ListView(padding:const EdgeInsets.all(10),children:[
    IndexPicker(selected:widget.selected,onChanged:widget.onIndex),const Section('Editable EMA'),
    Row(children:[Expanded(child:TextField(controller:fast,keyboardType:TextInputType.number,decoration:const InputDecoration(labelText:'EMA Fast'))),const SizedBox(width:8),Expanded(child:TextField(controller:slow,keyboardType:TextInputType.number,decoration:const InputDecoration(labelText:'EMA Slow')))]),
    const SizedBox(height:8),FilledButton(onPressed:(){final f=int.tryParse(fast.text)??8;final s=int.tryParse(slow.text)??13;widget.onChanged(f.clamp(2,50),s.clamp(3,100));},child:const Text('APPLY EMA')),
    const Section('Live Indicator Snapshot'),
    InfoRow('EMA Fast',_val(i['ema_fast'])),InfoRow('EMA Slow',_val(i['ema_slow'])),InfoRow('SMA 20',_val(i['sma20'])),
    InfoRow('EMA 50',_val(i['ema50'])),InfoRow('EMA 200',_val(i['ema200'])),
    InfoRow('RSI 14',_val(i['rsi14'])),InfoRow('MACD',_val(i['macd'])),InfoRow('MACD Histogram',_val(i['macd_hist'])),
    InfoRow('ATR 14',_val(i['atr14'])),InfoRow('VWAP',_val(i['vwap'])),
    InfoRow('Bollinger Mid',_val(i['bb_mid'])),InfoRow('Bollinger Upper',_val(i['bb_upper'])),InfoRow('Bollinger Lower',_val(i['bb_lower'])),
    InfoRow('Stochastic %K 14',_val(i['stochastic_k14'])),InfoRow('Stochastic %D 3',_val(i['stochastic_d3'])),
    InfoRow('Williams %R 14',_val(i['williams_r14'])),InfoRow('ROC 10 (%)',_val(i['roc10_pct'])),
    InfoRow('ADX 14',_val(i['adx14'])),InfoRow('Supertrend Direction',_val(i['supertrend_direction'])),
    InfoRow('Support 20',_val(i['support20'])),InfoRow('Resistance 20',_val(i['resistance20'])),
    InfoRow('Z-score 20',_val(i['zscore20'])),InfoRow('Realized Volatility 20',_val(i['realized_vol20'])),
    const Text('Advanced indicators require sufficient normalized OHLC history. N/A means the required history is not available; no values are fabricated.', style: TextStyle(fontSize: 11, color: Colors.white70)),
  ]);}
}

class SignalPage extends StatelessWidget {
  const SignalPage({required this.backendUrl, required this.liveStatus, required this.index, required this.signals, required this.ai, required this.aiProviders, required this.tradePlans, required this.market, required this.onChanged, super.key});
  final String backendUrl;
  final Map<String, dynamic> liveStatus;
  final String index;
  final Map<String, dynamic> signals;
  final Map<String, dynamic> ai;
  final Map<String, dynamic> aiProviders;
  final List<dynamic> tradePlans;
  final Map<String, dynamic> market;
  final ValueChanged<String> onChanged;


  @override
  Widget build(BuildContext context) {
    final s = Map<String, dynamic>.from(signals[index] as Map? ?? const {});
    final marketRow = Map<String, dynamic>.from(market[index] as Map? ?? const {});
    final reasons = (s['reason'] as List?) ?? const <dynamic>[];
    final guards = (s['guards'] as List?) ?? const <dynamic>[];
    final validation = Map<String, dynamic>.from(s['live_validation'] as Map? ?? const {});
    final validationBlocks = (validation['blocks'] as List?) ?? const <dynamic>[];
    final timeframeAnalysis = Map<String, dynamic>.from(s['timeframe_analysis'] as Map? ?? const {});
    final indicatorSummary = Map<String, dynamic>.from(s['indicator_summary'] as Map? ?? const {});
    final newsSentiment = Map<String, dynamic>.from(marketRow['news_sentiment'] as Map? ?? const {});
    final researchPack = Map<String, dynamic>.from(timeframeAnalysis['research_pack'] as Map? ?? const {});
    final researchChecks = Map<String, dynamic>.from(researchPack['checks'] as Map? ?? const {});
    final aiDecision = Map<String, dynamic>.from(ai[index] as Map? ?? const {});
    final providerMap = Map<String, dynamic>.from(aiProviders['providers'] as Map? ?? const {});
    final geminiProvider = Map<String, dynamic>.from(providerMap['gemini'] as Map? ?? const {});
    final openrouterProvider = Map<String, dynamic>.from(providerMap['openrouter'] as Map? ?? const {});
    final agentAnalysis = Map<String, dynamic>.from(aiDecision['agent_analysis'] as Map? ?? const {});
    final specialists = Map<String, dynamic>.from(agentAnalysis['specialists'] as Map? ?? const {});
    final decision = s['decision']?.toString() ?? '';
    final finalDecision = (validation['decision'] ?? 'WAIT').toString();
    final children = <Widget>[
      IndexPicker(selected: index, onChanged: onChanged),
      const Section('Signal'),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(finalDecision, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
              InfoRow('Market feed', (marketRow['feed_mode'] ?? 'NO DATA').toString()),
              InfoRow('Spot price', _val(marketRow['ltp'])),
              InfoRow('Market quote age', marketRow['age_seconds'] == null ? '—' : '${_val(marketRow['age_seconds'])} sec'),
              InfoRow('Snapshot time', (marketRow['timestamp'] ?? '—').toString()),
              InfoRow('Strategy candidate', (s['candidate_decision'] ?? (decision.isEmpty ? 'NO DATA' : decision)).toString()),
              InfoRow('10-minute stability', ((s['signal_stability'] as Map?)?['state'] ?? 'NOT CHECKED').toString()),
              InfoRow('Confidence', s['confidence'] == null ? '—' : '${s['confidence']}%'),
              InfoRow('Strike', s['strike']?.toString() ?? '—'),
              InfoRow('Option side', s['option_side']?.toString() ?? '—'),
              InfoRow('Entry', _val(s['entry'])),
              InfoRow('Stop Loss', _val(s['stop_loss'])),
              InfoRow('Target 1', _val(s['target'])),
              InfoRow('Target 2', _val((s['trade_plan'] as Map?)?['target2'])),
              InfoRow('Target 3', _val((s['trade_plan'] as Map?)?['target3'])),
              InfoRow('Entry TF', ((s['timeframe_analysis'] as Map?)?['entry_timeframe'] ?? '1m').toString()),
              InfoRow('Setup TF', ((s['timeframe_analysis'] as Map?)?['setup_timeframe'] ?? '5m').toString()),
              InfoRow('Regime TF', ((s['timeframe_analysis'] as Map?)?['regime_timeframe'] ?? '15m').toString()),
              InfoRow('Strike grade', ((s['trade_plan'] as Map?)?['selection_grade'] ?? '—').toString()),
              InfoRow('DTE / Lot', _val((s['trade_plan'] as Map?)?['dte']) + ' / ' + _val((s['trade_plan'] as Map?)?['lot_size'])),
              const Divider(),
              const Text('Why qualified / why rejected', style: TextStyle(fontWeight: FontWeight.w800)),
              ...reasons.map((r) => Text('• ' + r.toString())),
              ...guards.map((g) => Text('⚠ ' + g.toString())),
            ],
          ),
        ),
      ),
      const Section('Research Strategy Pack'),
      Card(child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          InfoRow('Candidate alignment', (researchPack['candidate_alignment'] ?? 'UNKNOWN').toString()),
          InfoRow('Evidence score', researchPack['evidence_score']?.toString() ?? '—'),
          InfoRow('Trend following', ((researchChecks['trend_following'] as Map?)?['state'] ?? 'UNKNOWN').toString()),
          InfoRow('Mean-reversion watch', ((researchChecks['mean_reversion'] as Map?)?['state'] ?? 'UNKNOWN').toString()),
          InfoRow('Option OI + premium flow', ((researchChecks['option_oi_premium_flow'] as Map?)?['state'] ?? 'UNKNOWN').toString()),
          InfoRow('Execution liquidity', ((researchChecks['execution_liquidity'] as Map?)?['state'] ?? 'UNKNOWN').toString()),
          const SizedBox(height: 4),
          Text((researchPack['safety_note'] ?? 'Research diagnostics are unavailable until the backend returns this payload.').toString(), style: const TextStyle(fontSize: 11)),
        ]),
      )),
      const Section('Technical Indicators & Session Sentiment'),
      Card(child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          InfoRow('EMA 8 / EMA 21', '${_val(indicatorSummary['ema_fast_8'])} / ${_val(indicatorSummary['ema_slow_21'])}'),
          InfoRow('EMA alignment', (indicatorSummary['ema_alignment'] ?? 'UNKNOWN').toString()),
          InfoRow('SMA 20 / SMA 50', '${_val(indicatorSummary['sma_20'])} / ${_val(indicatorSummary['sma_50'])}'),
          InfoRow('RSI 14', _val(indicatorSummary['rsi_14'])),
          InfoRow('RSI reversion', (indicatorSummary['rsi_reversion_signal'] ?? 'WAIT').toString()),
          InfoRow('MACD histogram', _val(indicatorSummary['macd_histogram'])),
          InfoRow('Underlying ATR 14', _val(indicatorSummary['underlying_atr_14'])),
          InfoRow('Session VWAP', _val(indicatorSummary['vwap'])),
          InfoRow('Session move', marketRow['day_move_pct'] == null ? '—' : '${marketRow['day_move_pct']}%'),
          InfoRow('Option PCR (near ATM)', _val(marketRow['pcr'])),
          InfoRow('Order-book imbalance', _val(marketRow['depth_imbalance'])),
          InfoRow('Session sentiment score', _val(marketRow['sentiment_score'])),
          InfoRow('Last-24h news sentiment', '${newsSentiment['label'] ?? 'UNKNOWN'} • ${newsSentiment['status'] ?? 'NOT_CONFIGURED'}'),
          InfoRow('News evidence', '${newsSentiment['article_count'] ?? 0} articles • ${((newsSentiment['sources'] as List?) ?? const []).join(', ')}'),
          Text((marketRow['sentiment_source'] ?? 'Session sentiment unavailable until fresh quotes arrive.').toString(), style: const TextStyle(fontSize: 11, color: Colors.white70)),
        ]),
      )),
      const Section('Multi-Agent AI Review'),
      Card(child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          InfoRow('AI mode', (agentAnalysis['mode'] ?? (geminiProvider['ok'] == true ? 'GEMINI CONNECTED • PRIMARY REVIEW' : openrouterProvider['ok'] == true ? 'OPENROUTER CONNECTED • FALLBACK REVIEW' : 'WAITING FOR GEMINI / OPENROUTER PROVIDER TEST')).toString()),
          InfoRow('Gemini provider', (geminiProvider['status'] ?? 'STATUS NOT CHECKED').toString()),
          InfoRow('Gemini model', (geminiProvider['model'] ?? '—').toString()),
          InfoRow('OpenRouter provider', (openrouterProvider['status'] ?? 'STATUS NOT CHECKED').toString()),
          InfoRow('OpenRouter model', (openrouterProvider['model'] ?? '—').toString()),
          InfoRow('Evidence supplied', (agentAnalysis['source_evidence_count'] ?? aiDecision['evidence_count'] ?? 0).toString()),
          ...specialists.entries.map((entry) {
            final report = Map<String, dynamic>.from(entry.value as Map? ?? const {});
            final status = (report['status'] ?? report['deterministic_status'] ?? 'UNKNOWN').toString();
            final view = (report['view'] ?? report['direction'] ?? report['deterministic_direction'] ?? 'UNKNOWN').toString();
            final rationale = (report['rationale'] ?? report['note'] ?? '').toString();
            final flags = (report['flags'] as List?)?.map((x) => x.toString()).toList() ?? const <String>[];
            return Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Card(
                child: ListTile(
                  dense: true,
                  title: Text(entry.key.replaceAll('_', ' ').toUpperCase(), style: const TextStyle(fontWeight: FontWeight.w800)),
                  subtitle: Text([view, status, rationale, if (flags.isNotEmpty) 'Flags: ${flags.join(', ')}'].where((x) => x.isNotEmpty).join(' • ')),
                ),
              ),
            );
          }),
          const SizedBox(height: 4),
          Text((agentAnalysis['safety_note'] ?? 'Specialist analysis appears after the cloud AI provider responds. Missing data must remain unavailable.').toString(), style: const TextStyle(fontSize: 11)),
        ]),
      )),
      const Section('Gemini Signal Review'),
      GeminiSignalReview(backendUrl: backendUrl, selectedIndex: index),
            const Section('Live AI Validation'),
      Card(child:Padding(
        padding:const EdgeInsets.all(12),
        child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
          InfoRow('Validation verdict',(validation['verdict'] ?? 'WAITING').toString()),
          InfoRow('BUY / SELL direction',(validation['market_direction'] ?? 'WAIT').toString()),
          InfoRow('F&O action',(validation['decision'] ?? 'WAIT').toString()),
          InfoRow('AI decision',(validation['ai_decision'] ?? 'NOT VALIDATED').toString()),
          InfoRow('Market tick age',validation['market_age_seconds'] == null ? '—' : '${validation['market_age_seconds']} sec'),
          InfoRow('Option quote age',validation['option_age_seconds'] == null ? '—' : '${validation['option_age_seconds']} sec'),
          InfoRow('AI result age',validation['ai_age_seconds'] == null ? '—' : '${validation['ai_age_seconds']} sec'),
          InfoRow('Reward / risk',validation['reward_risk']?.toString() ?? '—'),
          if (validationBlocks.isNotEmpty) ...[
            const Divider(),
            const Text('Validation blocks',style:TextStyle(fontWeight:FontWeight.w800)),
            ...validationBlocks.map((b)=>Text('⚠ ${b.toString()}')),
          ],
          const SizedBox(height:4),
          const Text('PASS requires fresh Angel One WebSocket data, a valid option quote, clear risk gates and a fresh AI decision agreeing with the strategy. Otherwise the final decision is WAIT.',style:TextStyle(fontSize:11)),
        ]),
      )),
      const Section('Signal-only mode'),
      Card(child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
          Text('This app provides analysis and signals only. It cannot place, modify or cancel broker orders.', style: TextStyle(fontWeight: FontWeight.w800)),
          SizedBox(height: 6),
          Text('A BUY/SELL signal is actionable only after the same side and strike pass the 10-minute stability gate. If data becomes stale or the candidate changes, the app returns to WAIT.', style: TextStyle(fontSize: 11)),
          SizedBox(height: 4),
          Text('This confirmation window does not guarantee profit or a minimum profitable holding period. Verify quotes and risk before acting in your separate broker app.', style: TextStyle(fontSize: 11, color: Colors.orangeAccent)),
        ]),
      )),
      const Section('Qualified trades across all indices'),
    ];
    if (tradePlans.isEmpty) {
      children.add(const StatusCard(text: '0 qualified trades right now.', good: true));
    } else {
      children.addAll(tradePlans.asMap().entries.map((e) => TradePlanCard(rank: e.key + 1, plan: Map<String, dynamic>.from(e.value as Map))));
    }
    return ListView(padding: const EdgeInsets.all(10), children: children);
  }
}

class RiskPage extends StatelessWidget {
  const RiskPage({required this.index, required this.signal, required this.plans, required this.market, required this.commodities, super.key});
  final String index;
  final Map<String, dynamic> signal;
  final List<dynamic> plans;
  final Map<String, dynamic> market;
  final List<dynamic> commodities;

  @override
  Widget build(BuildContext context) {
    final guards = (signal['guards'] as List?) ?? const <dynamic>[];
    final indexPlans = plans.where((p) => p is Map && p['index']?.toString().toUpperCase() == index.toUpperCase()).map((p) => Map<String,dynamic>.from(p as Map)).toList();
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        Section('Risk — ' + index),
        RiskCalculator(
          selectedIndex: index,
          marketByIndex: market,
          commodities: commodities,
        ),
        InfoRow('Entry', _val(signal['entry'])),
        InfoRow('Stop Loss', _val(signal['stop_loss'])),
        InfoRow('Target', _val(signal['target'])),
        InfoRow('Invalidation', guards.join(', ')),
        StatusCard(
          text: indexPlans.isEmpty
              ? 'No qualified trade plan for ' + index + '.'
              : indexPlans.length.toString() + ' qualified plan(s) for ' + index + ' currently pass the gates.',
          good: indexPlans.isNotEmpty,
        ),
        ...indexPlans.asMap().entries.map((e) => TradePlanCard(rank:e.key + 1, plan:e.value)),
      ],
    );
  }
}

class CommodityPage extends StatelessWidget {
  const CommodityPage({required this.items, super.key});
  final List<dynamic> items;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(10),
    children: [
      const Section('MCX Commodities — Angel One market feed'),
      const Text('Front-expiry commodity futures. Live status is shown only when the quote timestamp is fresh; stale or missing prices are not treated as live.', style: TextStyle(fontSize: 12)),
      if (items.isEmpty)
        const StatusCard(text: 'No commodity quotes yet. Connect Angel One and sync the instrument master; MCX feed may be unavailable outside market hours.', good: false),
      ...items.map((raw) {
        final item = Map<String, dynamic>.from(raw as Map);
        final live = item['live'] == true;
        return Card(child: ListTile(
          leading: Icon(Icons.show_chart, color: live ? Colors.greenAccent : Colors.orangeAccent),
          title: Text((item['name'] ?? item['symbol'] ?? 'Commodity').toString(), style: const TextStyle(fontWeight: FontWeight.w800)),
          subtitle: Text('Symbol: ${item['symbol'] ?? '—'} • Expiry: ${item['expiry'] ?? '—'}\nTrend: ${item['trend'] ?? 'UNKNOWN'} • Sentiment: ${item['sentiment_label'] ?? 'UNKNOWN'}\nSignal: ${item['decision'] ?? 'WAIT'} • Candidate: ${item['candidate_decision'] ?? 'WAIT'}\nEntry: ${_val(item['entry'])} • SL: ${_val(item['stop_loss'])} • Target: ${_val(item['target'])}\nStability: ${(item['signal_stability'] as Map?)?['state'] ?? 'BLOCKED'} • Lot: ${item['lotsize'] ?? '—'} • Age: ${item['age_seconds'] ?? '—'}s'),
          isThreeLine: true,
          trailing: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text(item['ltp'] == null ? '—' : '₹${_val(item['ltp'])}', style: const TextStyle(fontWeight: FontWeight.w900)),
            Text(live ? 'LIVE' : 'STALE', style: TextStyle(fontSize: 10, color: live ? Colors.greenAccent : Colors.orangeAccent)),
          ]),
        ));
      }),
    ],
  );
}

class ApiPage extends StatefulWidget {
  const ApiPage({required this.backendUrl,required this.signalBackendUrl,required this.feed,required this.storeDiagnostics,required this.market,required this.onSaved,super.key});
  final String backendUrl;
  final String signalBackendUrl;
  final Map<String,dynamic> feed,storeDiagnostics,market;
  final ValueChanged<String> onSaved;
  @override State<ApiPage> createState()=>_ApiPageState();
}
class _ApiPageState extends State<ApiPage> {
  final angelKey=TextEditingController(), client=TextEditingController(), pin=TextEditingController(), totp=TextEditingController();
  bool working=false;
  bool rememberCredentials=true;
  Map<String,dynamic> savedStatus=const {};
  String message='Connect once and choose Remember credentials. PIN and tokens are encrypted on the backend; TOTP is never saved.';

  @override
  void initState() {
    super.initState();
    loadSavedStatus();
  }

  Future<void> loadSavedStatus() async {
    try {
      final result=await FreshApi(widget.signalBackendUrl.trim()).angelStatus();
      if(!mounted)return;
      setState(()=>savedStatus=result);
      if(result['stored_session']==true) {
        setState(()=>message='Active Angel One session found. A fresh TOTP is needed only if the broker session expires.');
      } else if(result['stored_credentials']==true) {
        setState(()=>message='Encrypted credentials found. Enter the current six-digit TOTP to reconnect after a backend restart.');
      }
    } catch (_) {}
  }

  Map<String,dynamic> payload()=>{
    'angel_api_key':angelKey.text.trim().isEmpty?null:angelKey.text.trim(),
    'angel_client_code':client.text.trim().isEmpty?null:client.text.trim(),
    'angel_pin':pin.text.trim().isEmpty?null:pin.text.trim(),
    'angel_totp':totp.text.trim().isEmpty?null:totp.text.trim(),
    'remember_credentials':rememberCredentials,
  };

  Future<void> connect() async {
    setState(()=>working=true);
    try {
      final api=FreshApi(widget.signalBackendUrl.trim());
      final result=await api.connectAngel(payload());
      if (result['authenticated'] != true ||
          result['has_jwt_token'] != true ||
          result['has_feed_token'] != true) {
        final detail = (result['login_message'] ?? result['message'] ??
            'Angel One did not return a verified authenticated session.').toString();
        throw Exception(detail);
      }
      pin.clear();
      totp.clear();
      if(!mounted)return;
      setState(()=>message=result['session_restored']==true
          ? 'Saved Angel session restored. No new TOTP login was needed.'
          : 'Angel One authenticated. Credentials: ${rememberCredentials?'saved encrypted':'not saved'}; TOTP was not saved.');
      await loadSavedStatus();
      widget.onSaved(widget.backendUrl);
    } catch(e) {
      if(mounted)setState(()=>message='Angel connection failed: ${e.toString().replaceFirst('Exception: ','')}');
    } finally {if(mounted)setState(()=>working=false);}
  }

  @override Widget build(BuildContext context)=>ListView(padding:const EdgeInsets.all(10),children:[
    const Section('Angel One • SmartAPI'),
    ListTile(
      dense: true,
      leading: const Icon(Icons.cloud_done_outlined),
      title: const Text('Live signal service'),
      subtitle: SelectableText(widget.signalBackendUrl),
    ),
    if(savedStatus['stored_session']==true || savedStatus['stored_credentials']==true) Card(child:ListTile(
      leading:Icon(savedStatus['stored_session']==true?Icons.verified_user:Icons.lock_outline,color:savedStatus['stored_session']==true?Colors.greenAccent:Colors.orangeAccent),
      title:Text(savedStatus['stored_session']==true?'Active Angel One session':'Encrypted Angel credentials saved'),
      subtitle:Text('Client ID: ${savedStatus['client_code']??'saved'} • API Key: ${savedStatus['stored_api_key']==true?'saved':''} • MPIN: ${savedStatus['stored_pin']==true?'saved':''}'),
      trailing:const Icon(Icons.lock),
    )),
    field(angelKey,'API Key (required for first login)',true),
    field(client,'Client ID (required for first login)',false),
    field(pin,'MPIN / PIN (required for first login)',true),
    field(totp,'Current TOTP (only for fresh login)',true),
    CheckboxListTile(
      contentPadding:EdgeInsets.zero,
      value:rememberCredentials,
      onChanged:working?null:(v)=>setState(()=>rememberCredentials=v??true),
      title:const Text('Remember API Key, Client ID and MPIN (encrypted)'),
      subtitle:const Text('TOTP and generated JWT/feed tokens are not persisted. Turn off to delete previously saved credentials. A fresh TOTP may be required after backend restart.'),
      controlAffinity:ListTileControlAffinity.leading,
    ),
    FilledButton.icon(onPressed:working?null:connect,icon:const Icon(Icons.link),label:Text(working?'CONNECTING…':(savedStatus['stored_session']==true?'RESTORE / CONNECT':(savedStatus['stored_credentials']==true?'RECONNECT WITH TOTP':'CONNECT ANGEL ONE')))),
    const SizedBox(height:10),Text(message),
    const Section('Live Feed Diagnostics'),
    InfoRow('Angel authenticated',widget.feed['authenticated']==true?'YES':'NO'),
    InfoRow('Saved session',widget.feed['stored_session']==true?'YES':'NO'),
    InfoRow('WebSocket object',widget.feed['stream_started']==true?'CREATED':'NOT STARTED'),
    InfoRow('WebSocket open',widget.feed['stream_open']==true?'YES':'NO'),
    InfoRow('WebSocket tick count',(widget.feed['tick_count']??0).toString()),
    InfoRow('Unique tokens seen',(widget.feed['unique_tokens_seen']??widget.storeDiagnostics['unique_tokens']??0).toString()),
    InfoRow('Last WS tick age',widget.feed['last_tick_age_seconds']==null?'NO TICK':_val(widget.feed['last_tick_age_seconds'])+'s'),
    InfoRow('Store update count',(widget.storeDiagnostics['update_count']??0).toString()),
    InfoRow('Last store update age',widget.storeDiagnostics['last_update_age_seconds']==null?'NO DATA':_val(widget.storeDiagnostics['last_update_age_seconds'])+'s'),
    InfoRow('Feed error',(widget.feed['last_error']??'None').toString()),
    const Section('Per-index feed'),
    ...widget.market.entries.map((entry){final m=Map<String,dynamic>.from(entry.value as Map? ?? const {});return Card(child:ListTile(title:Text(entry.key),subtitle:Text('LTP '+_val(m['ltp'])+' • age '+_val(m['age_seconds'])+'s'),trailing:Text((m['feed_mode']??m['last_fetch_label']??'NO DATA').toString())));}),
    const SizedBox(height:12),
    const Text('The app attempts saved-session restore automatically. A fresh TOTP is needed only after the broker session expires or is rejected. LIVE means recent market ticks, not just successful login.',style:TextStyle(fontSize:12)),
  ]);

  Widget field(TextEditingController c,String label,bool secret)=>Padding(padding:const EdgeInsets.only(bottom:8),child:TextField(controller:c,obscureText:secret,decoration:InputDecoration(labelText:label)));
  @override void dispose(){for(final c in [angelKey,client,pin,totp]){c.dispose();}super.dispose();}
}

class AiAccessPage extends StatefulWidget {
  const AiAccessPage({required this.backendUrl, super.key});
  final String backendUrl;
  @override State<AiAccessPage> createState()=>_AiAccessState();
}
class _AiAccessState extends State<AiAccessPage>{
  bool working=false,checking=false,searchWorking=false;
  String message='Cloud AI status has not been checked.';
  Map<String,Map<String,dynamic>> providers=const{};
  @override void initState(){super.initState();refresh();}
  Future<void> refresh() async {
    if (checking) return;
    setState(() => checking = true);
    final api = FreshApi(widget.backendUrl.trim());
    final next = <String, Map<String, dynamic>>{};
    try {
      final result = await api.postJson('/v1/providers/search/status', {});
      final raw = result['providers'];
      if (raw is Map) {
        for (final name in ['exa', 'tavily']) {
          final value = raw[name];
          if (value is Map) next[name] = Map<String, dynamic>.from(value);
        }
      }
    } catch (error) {
      if (mounted) setState(() => message = 'Search provider check failed: ' + error.toString().replaceFirst('Exception: ', ''));
    }
    try {
      final result = await api.aiStatus();
      final raw = result['providers'];
      if (raw is Map) {
        for (final name in ['gemini', 'openrouter']) {
          final value = raw[name];
          if (value is Map) next[name] = Map<String, dynamic>.from(value);
        }
      } else {
        // Fresh-Apk's AI backend returns provider_health as a list. Configuration
        // alone is not a successful test, so keep every configured model red until
        // the explicit Test AI button returns a real completion.
        final health = result['provider_health'];
        if (health is List) {
          for (final item in health.whereType<Map>()) {
            final name = (item['name'] ?? '').toString().toLowerCase();
            if (!['gemini', 'openrouter'].contains(name)) continue;
            next[name] = <String, dynamic>{
              'configured': true,
              'ok': false,
              'working': false,
              'status': item['status'] == 'COOLDOWN' ? 'cooldown' : 'configured_not_tested',
              'model': item['model'] ?? item['model_name'] ?? 'model not reported',
              'last_error': item['last_error'],
            };
          }
        }
        for (final name in ['gemini', 'openrouter']) {
          next.putIfAbsent(name, () => <String, dynamic>{
            'configured': false, 'ok': false, 'working': false, 'status': 'not_configured',
          });
        }
      }
    } catch (error) {
      if (mounted) setState(() => message = 'AI provider status failed: ' + error.toString().replaceFirst('Exception: ', ''));
    }
    if (mounted) setState(() { providers = next; checking = false; });
  }

  Future<void> test() async {
    setState(() => working = true);
    try {
      final result = await FreshApi(widget.backendUrl.trim()).testAIProviders();
      final checks = (result['checks'] as List? ?? const []);
      final updated = <String, Map<String, dynamic>>{...providers};
      for (final item in checks.whereType<Map>()) {
        final name = (item['provider'] ?? '').toString();
        if (name == 'gemini' || name == 'openrouter') {
          final check = Map<String, dynamic>.from(item);
          check['configured'] = item['configured'] == true;
          check['status'] = check['ok'] == true ? 'ok' : (item['status'] ?? item['error'] ?? 'test_failed').toString();
          updated[name] = check;
        }
      }
      final details = checks.whereType<Map>().map((item) {
        final name = (item['provider'] ?? 'provider').toString().toUpperCase();
        final status = (item['status'] ?? (item['ok'] == true ? 'working' : 'not_working')).toString();
        final error = (item['error'] ?? '').toString();
        return '$name: $status${error.isEmpty ? '' : ' ($error)'}';
      }).join(' • ');
      final notice = (result['message'] ?? details).toString();
      if (mounted) {
        setState(() { providers = updated; message = '$notice • $details'; });
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$notice • $details'), duration: const Duration(seconds: 6)));
      }
    } catch (error) {
      if (mounted) setState(() => message = 'Cloud AI test failed: ' + error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => working = false);
    }
  }

  Future<void> testSearch() async {
    if (searchWorking) return;
    setState(() => searchWorking = true);
    try {
      final result = await FreshApi(widget.backendUrl.trim()).postJson('/v1/providers/search/test', {});
      final checks = (result['checks'] as List? ?? const []);
      final updated = <String, Map<String, dynamic>>{...providers};
      for (final item in checks.whereType<Map>()) {
        final name = (item['provider'] ?? '').toString();
        if (name == 'exa' || name == 'tavily') updated[name] = Map<String, dynamic>.from(item);
      }
      final details = checks.whereType<Map>().map((item) {
        final name = (item['provider'] ?? 'provider').toString().toUpperCase();
        final status = (item['status'] ?? (item['ok'] == true ? 'ok' : 'not_working')).toString();
        final error = (item['error'] ?? '').toString();
        final count = item['result_count'];
        return '$name: $status${count == null ? '' : ' • $count results'}${error.isEmpty ? '' : ' ($error)'}';
      }).join(' • ');
      final notice = (result['message'] ?? details).toString();
      if (mounted) {
        setState(() { providers = updated; message = '$notice • $details'; });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$notice • $details'), duration: const Duration(seconds: 6)),
        );
      }
    } catch (error) {
      if (mounted) setState(() => message = 'Search provider test failed: ${error.toString().replaceFirst('Exception: ', '')}');
    } finally {
      if (mounted) setState(() => searchWorking = false);
    }
  }

  Widget provider(String name) {
    final data = providers[name];
    final configured = data?['configured'] == true;
    final ok = data?['working'] == true || data?['ok'] == true;
    final status = (data?['status'] ?? '').toString();
    final label = data == null ? 'CHECK REQUIRED'
        : ok ? 'WORKING'
        : !configured ? 'NOT CONFIGURED'
        : status == 'configured_not_tested' ? 'NOT TESTED' : 'NOT WORKING';
    final color = data == null ? Colors.blueGrey
        : ok ? const Color(0xFF35D39A) : const Color(0xFFFF6577);
    final title = switch (name) {
      'exa' => 'Exa Search',
      'tavily' => 'Tavily Search',
      'openrouter' => 'OpenRouter',
      _ => name,
    };
    final detail = name == 'exa' || name == 'tavily'
        ? (data == null ? 'Not checked' : '$label • ${data['result_count'] ?? data['evidence_count'] ?? 0} result(s)')
        : (data == null ? 'Not checked' : '$label • ${data['model'] ?? 'model not reported'}');
    return Card(child: ListTile(
      leading: Icon(Icons.circle, size: 13, color: color),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
      subtitle: Text(detail),
      trailing: Text(label, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w900)),
    ));
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(14), children: [
    const Section('CLOUD AI • GEMINI CHAT + PROVIDER VALIDATION'),
    Card(child: ListTile(
      leading: Icon(
        providers['gemini']?['ok'] == true ? Icons.cloud_done : Icons.cloud_off,
        color: providers['gemini']?['ok'] == true ? const Color(0xFF35D39A) : const Color(0xFFFF6577),
        size: 30,
      ),
      title: const Text('Gemini Cloud Validation'),
      subtitle: Text(
        '${providers['gemini']?['status'] ?? 'not tested'} • AI remains advisory; deterministic freshness and risk gates control trade eligibility.',
      ),
    )),
    FilledButton.icon(onPressed: working ? null : test, icon: const Icon(Icons.psychology), label: Text(working ? 'TESTING GEMINI + OPENROUTER…' : 'TEST GEMINI + OPENROUTER')),
    const SizedBox(height: 10),
    Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(message))),
    const Section('LLM PROVIDERS • GEMINI + OPENROUTER'),
    provider('gemini'), provider('openrouter'),
    OutlinedButton.icon(onPressed: checking ? null : refresh, icon: const Icon(Icons.refresh), label: Text(checking ? 'CHECKING…' : 'REFRESH LLM STATUS')),
    const Section('SEARCH EVIDENCE • BACKEND CONFIGURED'),
    provider('exa'), provider('tavily'),
    FilledButton.icon(onPressed: searchWorking ? null : testSearch, icon: const Icon(Icons.travel_explore), label: Text(searchWorking ? 'TESTING EXA + TAVILY…' : 'TEST EXA + TAVILY')),
    OutlinedButton.icon(onPressed: checking ? null : refresh, icon: const Icon(Icons.refresh), label: Text(checking ? 'CHECKING…' : 'REFRESH EXA / TAVILY STATUS')),
    const SizedBox(height: 8),
    const Text('Provider keys remain on Railway. Green means a real provider test succeeded; configured-only or untested providers remain red until tested.', style: TextStyle(fontSize: 12, color: Colors.white60)),
  ]);
}

class ProCandlestickChart extends StatefulWidget {
  const ProCandlestickChart({required this.index,required this.market,required this.signal,super.key});
  final String index;
  final Map<String,dynamic> market,signal;
  @override State<ProCandlestickChart> createState()=>_ProCandlestickChartState();
}
class _ProCandlestickChartState extends State<ProCandlestickChart> {
  String timeframe='5m';
  @override Widget build(BuildContext context) {
    final all=Map<String,dynamic>.from(widget.market['timeframes'] as Map? ?? const{});
    final bars=(all[timeframe] as List? ?? const[]).whereType<Map>().map((x)=>Map<String,dynamic>.from(x)).toList();
    final indicators=Map<String,dynamic>.from(widget.signal['indicators'] as Map? ?? const{});
    return Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
      Row(children:[const Expanded(child:Text('PRO CHART',style:TextStyle(fontSize:16,fontWeight:FontWeight.w900,letterSpacing:1))),Text('${bars.length} bars',style:const TextStyle(fontSize:11,color:Colors.white60))]),
      const SizedBox(height:8),
      SegmentedButton<String>(segments:const [ButtonSegment(value:'1m',label:Text('1m')),ButtonSegment(value:'5m',label:Text('5m')),ButtonSegment(value:'15m',label:Text('15m'))],selected:{timeframe},onSelectionChanged:(v)=>setState(()=>timeframe=v.first)),
      const SizedBox(height:10),
      if(bars.length<2) const SizedBox(height:210,child:Center(child:Column(mainAxisAlignment:MainAxisAlignment.center,children:[Icon(Icons.candlestick_chart,size:36,color:Colors.white38),SizedBox(height:8),Text('Waiting for real candle history'),Text('No synthetic candles are displayed',style:TextStyle(fontSize:11,color:Colors.white54))])))
      else SizedBox(height:240,width:double.infinity,child:CustomPaint(painter:ProCandlePainter(bars))),
      const SizedBox(height:6),
      Wrap(spacing:12,runSpacing:6,children:[_chartLegend(Colors.greenAccent,'Bull candle'),_chartLegend(Colors.redAccent,'Bear candle'),Text('VWAP ${_val(indicators['vwap'])}',style:const TextStyle(fontSize:11,color:Colors.white70))]),
      const SizedBox(height:4),
      const Text('Chart source: backend-normalized Angel One candles. Visual aid only; signal/risk gates remain authoritative.',style:TextStyle(fontSize:10,color:Colors.white54)),
    ])));
  }
  Widget _chartLegend(Color color,String label)=>Row(mainAxisSize:MainAxisSize.min,children:[Container(width:8,height:8,decoration:BoxDecoration(color:color,shape:BoxShape.circle)),const SizedBox(width:4),Text(label,style:const TextStyle(fontSize:10,color:Colors.white70))]);
}
class ProCandlePainter extends CustomPainter {
  ProCandlePainter(this.bars);
  final List<Map<String,dynamic>> bars;
  @override void paint(Canvas canvas,Size size) {
    final valid=bars.where((b)=>['open','high','low','close'].every((k)=>b[k] is num)).toList();
    if(valid.length<2)return;
    final shown=valid.length>55?valid.sublist(valid.length-55):valid;
    final values=<double>[];
    for(final b in shown){values.addAll([for(final k in ['high','low']) (b[k] as num).toDouble()]);}
    var minP=values.reduce((a,b)=>a<b?a:b),maxP=values.reduce((a,b)=>a>b?a:b);
    if(maxP-minP<0.000001){minP-=1;maxP+=1;}
    final pad=12.0,plotH=size.height-24,plotW=size.width-44;
    final y=(double p)=>pad+(maxP-p)/(maxP-minP)*plotH;
    final grid=Paint()..color=Colors.white.withOpacity(.08)..strokeWidth=1;
    final labelStyle=TextStyle(color:Colors.white.withOpacity(.55),fontSize:9);
    for(var i=0;i<5;i++){final yy=pad+i*plotH/4;canvas.drawLine(Offset(0,yy),Offset(plotW,yy),grid);final price=maxP-i*(maxP-minP)/4;final tp=TextPainter(text:TextSpan(text:price.toStringAsFixed(1),style:labelStyle),textDirection:TextDirection.ltr)..layout(maxWidth:42);tp.paint(canvas,Offset(plotW+3,yy-5));}
    final step=plotW/shown.length,bodyW=(step*.58).clamp(2.0,10.0).toDouble();
    for(var i=0;i<shown.length;i++){
      final b=shown[i],open=(b['open'] as num).toDouble(),high=(b['high'] as num).toDouble(),low=(b['low'] as num).toDouble(),close=(b['close'] as num).toDouble();
      final x=i*step+step/2,color=close>=open?Colors.greenAccent:Colors.redAccent;
      final wick=Paint()..color=color..strokeWidth=1.2;
      canvas.drawLine(Offset(x,y(high)),Offset(x,y(low)),wick);
      final top=y(open<close?close:open),bottom=y(open>close?open:close);
      final rect=Rect.fromLTRB(x-bodyW/2,top,x+bodyW/2,(bottom-top).abs()<2?top+2:bottom);
      canvas.drawRect(rect,Paint()..color=color);
    }
    final last=shown.last,close=(last['close'] as num).toDouble(),line=Paint()..color=Colors.cyanAccent.withOpacity(.8)..strokeWidth=1..style=PaintingStyle.stroke;
    canvas.drawLine(Offset(0,y(close)),Offset(plotW,y(close)),line);
  }
  @override bool shouldRepaint(covariant ProCandlePainter oldDelegate)=>oldDelegate.bars!=bars;
}

class StatusCard extends StatelessWidget { const StatusCard({required this.text,required this.good,super.key}); final String text; final bool good; @override Widget build(BuildContext context)=>Card(child:Padding(padding:const EdgeInsets.all(12),child:Row(children:[Icon(good?Icons.verified:Icons.info_outline),const SizedBox(width:8),Expanded(child:Text(text))]))); }
class HeroCard extends StatelessWidget { const HeroCard({required this.index,required this.connected,super.key}); final String index; final bool connected; @override Widget build(BuildContext context)=>Card(child:Padding(padding:const EdgeInsets.all(16),child:Row(children:[CircleAvatar(radius:26,child:Text(index.substring(0,1))),const SizedBox(width:12),Expanded(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(index,style:const TextStyle(fontSize:22,fontWeight:FontWeight.w900)),Text(connected?'LIVE • broker connected':'WAITING • connect broker',style:const TextStyle(fontSize:12))])),const Icon(Icons.auto_graph)]))); }
class Metric extends StatelessWidget { const Metric({required this.title,required this.value,super.key}); final String title,value; @override Widget build(BuildContext context)=>Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(title,style:const TextStyle(fontSize:12)),const SizedBox(height:5),Text(value,style:const TextStyle(fontSize:18,fontWeight:FontWeight.w900))]))); }
class Section extends StatelessWidget { const Section(this.text,{super.key}); final String text; @override Widget build(BuildContext context)=>Padding(padding:const EdgeInsets.fromLTRB(4,16,4,8),child:Text(text,style:const TextStyle(fontSize:16,fontWeight:FontWeight.w800))); }
class InfoRow extends StatelessWidget { const InfoRow(this.left,this.right,{super.key}); final String left,right; @override Widget build(BuildContext context)=>Card(child:ListTile(title:Text(left),trailing:SizedBox(width:140,child:Text(right,maxLines:3,overflow:TextOverflow.ellipsis,textAlign:TextAlign.right,style:const TextStyle(fontWeight:FontWeight.w700,fontSize:12))))); }
class ChainRow extends StatelessWidget { const ChainRow(this.strike,this.ce,this.pe,{super.key}); final String strike,ce,pe; @override Widget build(BuildContext context)=>Card(child:Row(mainAxisAlignment:MainAxisAlignment.spaceBetween,children:[Padding(padding:const EdgeInsets.all(14),child:Text(ce)),Text(strike,style:const TextStyle(fontWeight:FontWeight.w900)),Padding(padding:const EdgeInsets.all(14),child:Text(pe))])); }
class OIBox extends StatelessWidget { const OIBox(this.title,this.hint,{super.key}); final String title,hint; @override Widget build(BuildContext context)=>Card(child:ListTile(leading:const Icon(Icons.swap_vert),title:Text(title,style:const TextStyle(fontWeight:FontWeight.w800)),subtitle:Text(hint),trailing:const Text('—'))); }
class IndexPicker extends StatelessWidget{
  const IndexPicker({required this.selected,required this.onChanged,super.key});final String selected;final ValueChanged<String> onChanged;
  @override Widget build(BuildContext context)=>DropdownButtonFormField<String>(initialValue:selected,decoration:const InputDecoration(labelText:'Select Index / MCX Commodity'),items:optionUnderlyings.map((i)=>DropdownMenuItem(value:i,child:Text(commodityOptionUnderlyings.contains(i) ? 'MCX • $i' : i))).toList(),onChanged:(v){if(v!=null)onChanged(v);});
}
class TradePlanCard extends StatelessWidget {
  const TradePlanCard({required this.rank, required this.plan, super.key});
  final int rank;
  final Map<String, dynamic> plan;

  @override
  Widget build(BuildContext context) {
    final reasons = (plan['reason'] as List?) ?? const <dynamic>[];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('#' + rank.toString() + ' ' + (plan['index'] ?? '').toString() + ' • ' + (plan['decision'] ?? '').toString(), style: const TextStyle(fontWeight: FontWeight.w900)),
            InfoRow('Confidence', (plan['confidence'] ?? 0).toString() + '%'),
            InfoRow('Strike', plan['strike']?.toString() ?? '—'),
            InfoRow('Entry / SL', _val(plan['entry']) + ' / ' + _val(plan['stop_loss'])),
            InfoRow('Target 1 / 2 / 3', _val(plan['target1']) + ' / ' + _val(plan['target2']) + ' / ' + _val(plan['target3'])),
            InfoRow('TF', (plan['regime_timeframe'] ?? '15m').toString() + ' → ' + (plan['setup_timeframe'] ?? '5m').toString() + ' → ' + (plan['entry_timeframe'] ?? '1m').toString()),
            InfoRow('Strike grade', (plan['selection_grade'] ?? '—').toString()),
            InfoRow('DTE / Lot', _val(plan['dte']) + ' / ' + _val(plan['lot_size'])),
            ...reasons.map((r) => Text('• ' + r.toString())),
          ],
        ),
      ),
    );
  }
}

String _val(dynamic v){if(v==null)return '—';if(v is num)return v.toStringAsFixed(v.abs()>=100?2:3);return v.toString();}