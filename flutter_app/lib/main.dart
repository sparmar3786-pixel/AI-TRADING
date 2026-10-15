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
import 'pdf_report_solutions_page.dart';
import 'ai_chat_page.dart';
import 'quant_engine_lab_page.dart';

const tabs = ['Dashboard','Market','Option Chain','OI Lab','Indicators','Signals','Risk','Backtesting','API','AI Access','Data Health','API & Railway','Trading Setup','Research Engines','5-Layer Quant Signal Engine','Broker Home (Prototype)','PDF Reports','AI Chat','Quant Engine Lab'];
const indexes = ['NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY','SENSEX','BANKEX'];

void main() {
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
  String selectedIndex = 'NIFTY';
  bool apiOnline = false;
  bool signalsEndpointOnline = false;
  String? signalsFetchError;
  bool angelOnline = false;
  Map<String,dynamic> liveTrading = const {};
  Map<String,dynamic> ai = const {};
  Map<String,dynamic> feed = const {};
  Map<String,dynamic> storeDiagnostics = const {};
  Map<String,dynamic> systemDiagnostics = const {};
  String? systemDiagnosticsError;
  Map<String,dynamic> signals = const {};
  bool _refreshing = false;
  Map<String,dynamic> market = const {};
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
    result['trade_plans'] = <dynamic>[];
    result['qualified_trade_count'] = 0;
    return result;
  }

  Future<void> refresh() async {
    if (_refreshing) return;
    _refreshing = true;
    Map<String, dynamic> latestSystemDiagnostics = const {};
    String? latestSystemDiagnosticsError;
    try {
      final api = FreshApi(backendUrl);
      await api.health();
      // Broker/session diagnostics must not prevent the independent signal
      // endpoint from being queried. A broken /v1/angel/status route used to
      // abort refresh here and incorrectly mask signal/API diagnostics.
      Map<String,dynamic> a = const {};
      String? angelStatusError;
      try {
        a = await api.angelStatus();
      } catch (e) {
        angelStatusError = e.toString().replaceFirst('Exception: ', '');
      }
      Map<String,dynamic> liveStatus = const {};
      try { liveStatus = await api.liveExecutionStatus(); } catch (_) {}
      Map<String,dynamic> s;
      try {
        s = await api.signals(emaFast: emaFast, emaSlow: emaSlow);
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
      try {
        latestSystemDiagnostics = await api.systemDiagnostics();
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
        ai = (s['ai'] as Map?)?.cast<String,dynamic>() ?? {};
        feed = (s['feed'] as Map?)?.cast<String,dynamic>() ?? {};
        storeDiagnostics = (s['store'] as Map?)?.cast<String,dynamic>() ?? {};
        signals = (s['signals'] as Map?)?.cast<String,dynamic>() ?? {};
        market = (s['market'] as Map?)?.cast<String,dynamic>() ?? {};
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
        tradePlans = ((s['trade_plans'] as List?) ?? const []).whereType<Map>().map((plan) => Map<String, dynamic>.from(plan)).toList();
        qualifiedCount = (s['qualified_trade_count'] as num?)?.toInt() ?? tradePlans.length;
        lastFetch = s['last_fetch']?.toString();
        status = lastFetch != null ? 'Backend unavailable — showing last fetched market data. Error: ${signalsFetchError ?? 'request failed'}' : 'Backend offline or unreachable: ${signalsFetchError ?? 'health check failed'}';
      });
    } finally {
      _refreshing = false;
    }
  }

  bool get _marketOpenNow {
    final ist = DateTime.now().toUtc().add(const Duration(hours: 5, minutes: 30));
    if (ist.weekday == DateTime.saturday || ist.weekday == DateTime.sunday) return false;
    final minutes = ist.hour * 60 + ist.minute;
    return minutes >= (9 * 60 + 15) && minutes <= (15 * 60 + 30);
  }

  String get _appBarStatus {
    if (!apiOnline) return "API OFFLINE";
    if (!signalsEndpointOnline) return "API UP • DATA ERROR";
    if (!_marketOpenNow) return "API UP • MARKET CLOSED";
    if (status == "LIVE market feed connected.") return "API LIVE";
    if (status.startsWith("Backend online")) return "API UP • WAITING DATA";
    return "API UP • DATA ERROR";
  }

  Color get _appBarStatusColor {
    if (_appBarStatus == "API LIVE") return Colors.greenAccent;
    if (_appBarStatus == "API OFFLINE") return Colors.redAccent;
    if (_appBarStatus == "API UP • MARKET CLOSED") return const Color(0xFF94A3B8);
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

  Map<String,dynamic> _signal(String i) => Map<String,dynamic>.from(signals[i] as Map? ?? const {});
  Map<String,dynamic> _market(String i) => Map<String,dynamic>.from(market[i] as Map? ?? const {});

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
          Text(_appBarStatus, style: TextStyle(fontSize:11, color: _appBarStatusColor)),
        ]))],
        bottom: TabBar(isScrollable: true, tabAlignment: TabAlignment.start, tabs: tabs.map((t)=>Tab(text:t)).toList()),
      ),
      body: TabBarView(children: [
        DashboardPage(index:selectedIndex, connected:status == 'LIVE market feed connected.', status:status, signals:signals, market:market, tradePlans:tradePlans, qualifiedCount:qualifiedCount, lastFetch:lastFetch, onSelected:(v)=>setState(()=>selectedIndex=v)),
        MarketPage(selected:selectedIndex,onChanged:(v)=>setState(()=>selectedIndex=v), signal:_signal(selectedIndex), market:_market(selectedIndex)),
        ChainPage(selected:selectedIndex,onChanged:(v)=>setState(()=>selectedIndex=v), market:_market(selectedIndex)),
        OIPage(signals:signals),
        IndicatorsPage(selected:selectedIndex,signal:_signal(selectedIndex),fast:emaFast,slow:emaSlow,onChanged:(f,s){setState((){emaFast=f;emaSlow=s;});refresh();},onIndex:(v)=>setState(()=>selectedIndex=v)),
        SignalPage(backendUrl:backendUrl,liveStatus:liveTrading,index:selectedIndex,signals:signals,ai:ai,tradePlans:tradePlans,market:market,onChanged:(v)=>setState(()=>selectedIndex=v)),
        RiskPage(index:selectedIndex,signal:_signal(selectedIndex),plans:tradePlans),
        BacktestingPage(backendUrl: backendUrl),
        ApiPage(backendUrl:backendUrl,feed:feed,storeDiagnostics:storeDiagnostics,market:market,onSaved:(url){setState(()=>backendUrl=url);refresh();}),
        AiAccessPage(backendUrl: backendUrl),
        DataHealthPage(
          backendUrl: backendUrl,
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
        TradingSetupPage(backendUrl: backendUrl, apiOnline: apiOnline, signalsOnline: signalsEndpointOnline, angelOnline: angelOnline, market: market, signals: signals, ai: ai, liveStatus: liveTrading, lastFetch: lastFetch),
        ResearchEnginesPage(market: market, signals: signals, ai: ai, lastFetch: lastFetch, selectedIndex: selectedIndex, onIndexChanged: (value) => setState(() => selectedIndex = value)),
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
        BrokerHomePrototypePage(
          backendUrl: backendUrl,
          market: market,
          signals: signals,
          angelOnline: angelOnline,
          status: status,
          onIndexSelected: (value) => setState(() => selectedIndex = value),
        ),
        const PdfReportSolutionsPage(),
        AiChatPage(backendUrl: backendUrl, selectedIndex: selectedIndex),
        Builder(
          builder: (tabContext) => QuantEngineLabPage(
            backendUrl: backendUrl,
            index: selectedIndex,
            market: market,
            lastFetch: lastFetch,
            onOpenBacktest: () => DefaultTabController.of(tabContext).animateTo(tabs.indexOf('Backtesting')),
          ),
        ),
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
  19 => Icons.science_outlined,
  20 => Icons.library_books_outlined,
  21 => Icons.chat_bubble_outline,
  _ => Icons.layers_outlined,
};

class DataHealthPage extends StatelessWidget {
  const DataHealthPage({
    required this.backendUrl,
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
        ListTile(leading: const Icon(Icons.link), title: const Text('Configured backend'), subtitle: SelectableText(backendUrl)),
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
            subtitle: Text('Price: ${_val(row['ltp'])} • Age: ${row['age_seconds'] == null ? 'unknown' : '${_val(row['age_seconds'])} sec'} • ${row['feed_mode'] ?? 'NO DATA'}'),
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

class ResearchEnginesPage extends StatelessWidget {
  const ResearchEnginesPage({
    required this.market,
    required this.signals,
    required this.ai,
    required this.lastFetch,
    required this.selectedIndex,
    required this.onIndexChanged,
    super.key,
  });
  final Map<String, dynamic> market, signals, ai;
  final String? lastFetch;
  final String selectedIndex;
  final ValueChanged<String> onIndexChanged;

  static const sources = <(String, String, String)>[
  ];

  @override
  Widget build(BuildContext context) {
    final m = Map<String, dynamic>.from(market[selectedIndex] as Map? ?? const {});
    final s = Map<String, dynamic>.from(signals[selectedIndex] as Map? ?? const {});
    final indicators = Map<String, dynamic>.from(s['indicators'] as Map? ?? const {});
    final oi = Map<String, dynamic>.from(s['oi_summary'] as Map? ?? const {});
    final validation = Map<String, dynamic>.from(s['live_validation'] as Map? ?? const {});
    final tf = Map<String, dynamic>.from(s['timeframe_analysis'] as Map? ?? const {});
    final research = Map<String, dynamic>.from(tf['research_pack'] as Map? ?? const {});
    final checks = Map<String, dynamic>.from(research['checks'] as Map? ?? const {});
    final aiRow = Map<String, dynamic>.from(ai[selectedIndex] as Map? ?? const {});
    final chain = (m['option_chain'] as List?) ?? const <dynamic>[];
    final fresh = m['live'] == true;

    return ListView(padding: const EdgeInsets.all(12), children: [
      const Text('RESEARCH ENGINES • LIVE BACKEND OUTPUT', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 6),
      const Text('This tab shows the app’s actual indicator, OI, confluence and validation outputs from the backend.', style: TextStyle(color: Colors.white70, fontSize: 12)),
      const SizedBox(height: 10),
      IndexPicker(selected: selectedIndex, onChanged: onIndexChanged),
      Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(selectedIndex, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900))),
          _statusPill(fresh ? 'LIVE' : 'STALE / NO DATA', fresh ? Colors.greenAccent : Colors.orangeAccent),
        ]),
        Text('Spot LTP ₹${_val(m['ltp'])}', style: const TextStyle(fontSize: 25, fontWeight: FontWeight.w900, color: Color(0xFF12D6FF))),
        Text('Snapshot: ${m['timestamp'] ?? lastFetch ?? 'No snapshot'}', style: const TextStyle(fontSize: 11, color: Colors.white60)),
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
        const Text('OPTIONS / OPEN INTEREST ENGINE', style: TextStyle(fontWeight: FontWeight.w900)),
        InfoRow('CALL OI', _val(oi['call_oi'])),
        InfoRow('PUT OI', _val(oi['put_oi'])),
        InfoRow('PCR', _val(oi['pcr'])),
        InfoRow('OI regime', (oi['selected_oi_regime'] ?? oi['classification'] ?? 'UNKNOWN').toString()),
        InfoRow('Live option rows', chain.length.toString()),
        const Divider(height: 22),
        const Text('RESEARCH PACK & CONFLUENCE', style: TextStyle(fontWeight: FontWeight.w900)),
        InfoRow('Candidate alignment', (research['candidate_alignment'] ?? 'UNKNOWN').toString()),
        InfoRow('Evidence alignment score', _val(research['evidence_score'])),
        InfoRow('Known directional checks', (research['known_directional_checks'] ?? 0).toString()),
        for (final entry in checks.entries)
          if (entry.value is Map)
            InfoRow(entry.key.replaceAll('_', ' '), (entry.value as Map)['state']?.toString() ?? 'UNKNOWN'),
        const Divider(height: 22),
        const Text('SIGNAL & VALIDATION OUTPUT', style: TextStyle(fontWeight: FontWeight.w900)),
        InfoRow('Strategy candidate', (s['decision'] ?? 'NO DATA').toString()),
        InfoRow('Validated decision', (validation['decision'] ?? 'WAIT').toString()),
        InfoRow('Validation verdict', (validation['verdict'] ?? 'NOT VALIDATED').toString()),
        InfoRow('AI action', (aiRow['action'] ?? 'AI NOT READY').toString()),
        InfoRow('Blocked reasons', ((validation['blocks'] as List?) ?? const []).map((x) => x.toString()).join(', ').isEmpty ? 'None reported' : ((validation['blocks'] as List?) ?? const []).map((x) => x.toString()).join(', ')),
      ]))),
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
  final bool apiOnline, signalsOnline, angelOnline;
  final Map<String, dynamic> market, signals, ai, liveStatus;
  final String? lastFetch;

  static const sections = <(String, String)>[
    ('1 • Broker & Market Data', 'Angel One SmartAPI is the broker integration for this app. Live ticks, historical candles, instruments, option-chain/OI fields and feed freshness must be verified independently.'),
    ('2 • Strategy & Signal Engine', 'Run deterministic indicators and OI classification first; use AI only as an evidence-based interpretation layer. Missing, stale or conflicting data must result in WAIT / NO TRADE.'),
    ('3 • Signal Quality & Evidence Filter', 'Score independent evidence, reject stale quotes, require a minimum data-quality gate and avoid treating an AI confidence statement as a probability of profit.'),
    ('4 • Backtesting & Walk-Forward Validation', 'Use out-of-sample periods, walk-forward testing, slippage, brokerage, taxes/fees, option expiry and realistic fill assumptions. Avoid look-ahead bias and overfitting.'),
    ('5 • Risk & Trade Management', 'Require per-trade risk caps, max daily loss, max drawdown, max open positions, lot-size validation, spread/liquidity checks, kill switch and explicit handling of partial fills and rejected orders.'),
    ('6 • Order Execution & Trade Lifecycle', 'Real orders are deliberately gated. Confirm authentication, contract mapping, quote freshness, order book state, partial fills and exit handling before enabling live orders.'),
    ('7 • Monitoring, Alerts & Audit', 'Track WebSocket disconnects, stale data, API failures, rejected orders, latency, daily P&L, exposure and audit events. Alerts should never silently imply that an order filled.'),
    ('8 • Dashboard, Charts & Mobile UX', 'Keep compact F&O-first screens, clear data timestamps, candle timeframe controls, option-chain/strike view, signal explanation, risk card, execution mode and connection health.'),
    ('9 • Backend, Secrets & Deployment', 'Android → HTTPS Railway backend → Angel One REST/WebSocket → normalized store → strategy/risk gates → signal/monitoring APIs. Keep API keys, PIN and TOTP secrets off-device and out of the app.'),
  ];

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
        final aiReady = ai.values.whereType<Map>().any((row) => row['action'] != null);
        final checks = <(String, bool, String)>[
          ('1. Backend API', apiOnline, backendUrl),
          ('2. Angel One login', angelOnline, 'Authenticated session required'),
          ('3. Live market data', liveIndexes > 0, '$liveIndexes of ${indexes.length} indexes fresh'),
          ('4. Indicators & strategy engine', indicatorReady, 'Deterministic indicators and OI strategy output'),
          ('5. Option chain / OI', optionRows > 0, '$optionRows option quotes in latest snapshots'),
          ('6. Signal risk validation', validationReady, 'Fail-closed validation payload'),
          ('7. Historical backtest', angelOnline, 'Historical candle replay requires an authenticated Angel One session'),
          ('8. AI analysis', aiReady, 'Cloud AI result returned by backend'),
          ('9. Execution / order status', liveStatus.isNotEmpty, '${liveStatus['mode'] ?? 'Status not returned'} • live orders remain gated by risk and explicit approval'),
        ];
        return Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('LIVE SETUP CHECKLIST • 9 MODULES', style: TextStyle(fontWeight: FontWeight.w900)),
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
            ],
          ),
        ),
      const Card(child: Padding(
        padding: EdgeInsets.all(12),
        child: Text('This app is for decision support. Review historical assumptions and validate the live feed before any live order; live endpoints remain gated and are not a promise of profit.', style: TextStyle(fontSize: 12, color: Colors.white70)),
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
  const DashboardPage({required this.index,required this.connected,required this.status,required this.signals,required this.market,required this.tradePlans,required this.qualifiedCount,required this.lastFetch,required this.onSelected,super.key});
  final String index; final bool connected; final String status;
  final Map<String,dynamic> signals, market; final List<dynamic> tradePlans; final int qualifiedCount; final String? lastFetch;
  final ValueChanged<String> onSelected;
  @override Widget build(BuildContext context) {
    final s=Map<String,dynamic>.from(signals[index] as Map? ?? const {});
    final m=Map<String,dynamic>.from(market[index] as Map? ?? const {});
    return ListView(padding:const EdgeInsets.all(10),children:[
      StatusCard(text:status,good:status == 'LIVE market feed connected.'),
      if (lastFetch != null) Card(child: ListTile(leading: const Icon(Icons.history), title: const Text('Last market fetch'), subtitle: Text(lastFetch!), trailing: Text(status == 'LIVE market feed connected.' ? 'LIVE' : 'CACHED'))),
      DropdownButtonFormField<String>(initialValue:index,decoration:const InputDecoration(labelText:'Select Index'),items:indexes.map((i)=>DropdownMenuItem(value:i,child:Text(i))).toList(),onChanged:(v){if(v!=null)onSelected(v);}),
      Card(child:Padding(padding:const EdgeInsets.all(14),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        Text(index,style:const TextStyle(fontSize:24,fontWeight:FontWeight.w900)),
        InfoRow('LTP',_val(m['ltp'])),InfoRow('Decision',s['decision']?.toString()??'NO DATA'),
        InfoRow('Confidence',(s['confidence']??0).toString()+'%'),InfoRow('Regime',s['regime']?.toString()??'—'),
        InfoRow('Last fetch',m['timestamp']?.toString()??'—'),
      ]))),
      Row(children:[Expanded(child:Metric(title:'Qualified trades',value:qualifiedCount.toString()+' / 5')),Expanded(child:Metric(title:'Feed',value:status == 'LIVE market feed connected.'?'LIVE':'LAST'))]),
      const Section('Trade Plan — best qualified candidates'),
      if(tradePlans.isEmpty) const StatusCard(text:'0 qualified trades — no candidate passed all gates.',good:true)
      else ...tradePlans.asMap().entries.map((e)=>TradePlanCard(rank:e.key+1,plan:Map<String,dynamic>.from(e.value as Map))),
      const Section('Indian F&O Index Board'),
      GridView.count(shrinkWrap:true,physics:const NeverScrollableScrollPhysics(),crossAxisCount:2,childAspectRatio:1.48,crossAxisSpacing:8,mainAxisSpacing:8,children:indexes.map((i){final x=Map<String,dynamic>.from(signals[i] as Map? ?? const {});final mx=Map<String,dynamic>.from(market[i] as Map? ?? const {});final decision=(x['decision']??'NO DATA').toString();final bullish=decision=='CALL BUY';final bearish=decision=='PUT BUY';final color=bullish?Colors.greenAccent:bearish?Colors.redAccent:Colors.orangeAccent;return InkWell(onTap:()=>onSelected(i),borderRadius:BorderRadius.circular(14),child:Card(child:Padding(padding:const EdgeInsets.all(10),child:Column(crossAxisAlignment:CrossAxisAlignment.start,mainAxisAlignment:MainAxisAlignment.spaceBetween,children:[Row(children:[Expanded(child:Text(i,style:const TextStyle(fontWeight:FontWeight.w900,fontSize:15))),Icon(Icons.show_chart,color:color,size:18)]),Text('₹ ${_val(mx['ltp'])}',style:const TextStyle(fontSize:17,fontWeight:FontWeight.w800)),Container(padding:const EdgeInsets.symmetric(horizontal:7,vertical:4),decoration:BoxDecoration(color:color.withOpacity(.12),borderRadius:BorderRadius.circular(7)),child:Text(decision,style:TextStyle(fontSize:10,color:color,fontWeight:FontWeight.w900))),Text('${(x['confidence']??0)}% • ${(x['regime']??'—')}',style:const TextStyle(fontSize:10,color:Colors.white70))]))));}).toList()),
    ]);
  }
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
    const Section('Timeframe Data • broker candles only'),
    ...['15m','5m','1m'].map((tf){final arr=((market['timeframes'] as Map?)?[tf] as List?)??const[];final last=arr.isEmpty?null:Map<String,dynamic>.from(arr.last as Map);return Card(child:ListTile(title:Text(tf+' • '+arr.length.toString()+' bars'),subtitle:Text('O '+_val(last?['open'])+' H '+_val(last?['high'])+' L '+_val(last?['low'])+' C '+_val(last?['close'])+' • '+_val(last?['count'])+' ticks')));}),
  ]);
}

class ChainPage extends StatefulWidget {
  const ChainPage({required this.selected, required this.onChanged, required this.market, super.key});
  final String selected;
  final ValueChanged<String> onChanged;
  final Map<String, dynamic> market;
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
  const OIPage({required this.signals,super.key}); final Map<String,dynamic> signals;
  @override Widget build(BuildContext context)=>ListView(padding:const EdgeInsets.all(10),children:[
    const Section('OI Lab — all indices'),
    ...indexes.map((i){final s=Map<String,dynamic>.from(signals[i] as Map? ?? const {});final o=Map<String,dynamic>.from(s['oi_summary'] as Map? ?? const{});return Card(child:Padding(padding:const EdgeInsets.all(14),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
      Text(i,style:const TextStyle(fontSize:19,fontWeight:FontWeight.w900)),InfoRow('CALL OI',_val(o['call_oi'])),InfoRow('PUT OI',_val(o['put_oi'])),InfoRow('PCR',_val(o['pcr'])),InfoRow('Classification',o['classification']?.toString()??'—'),InfoRow('Selected OI regime',o['selected_oi_regime']?.toString()??'—'),
    ])));}),
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
  const SignalPage({required this.backendUrl, required this.liveStatus, required this.index, required this.signals, required this.ai, required this.tradePlans, required this.market, required this.onChanged, super.key});
  final String backendUrl;
  final Map<String, dynamic> liveStatus;
  final String index;
  final Map<String, dynamic> signals;
  final Map<String, dynamic> ai;
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
    final researchPack = Map<String, dynamic>.from(timeframeAnalysis['research_pack'] as Map? ?? const {});
    final researchChecks = Map<String, dynamic>.from(researchPack['checks'] as Map? ?? const {});
    final aiDecision = Map<String, dynamic>.from(ai[index] as Map? ?? const {});
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
      const Section('Multi-Agent AI Review'),
      Card(child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          InfoRow('AI mode', (agentAnalysis['mode'] ?? 'WAITING FOR OPENAI').toString()),
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
  const RiskPage({required this.index, required this.signal, required this.plans, super.key});
  final String index;
  final Map<String, dynamic> signal;
  final List<dynamic> plans;

  @override
  Widget build(BuildContext context) {
    final guards = (signal['guards'] as List?) ?? const <dynamic>[];
    final indexPlans = plans.where((p) => p is Map && p['index']?.toString().toUpperCase() == index.toUpperCase()).map((p) => Map<String,dynamic>.from(p as Map)).toList();
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        Section('Risk — ' + index),
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

class ApiPage extends StatefulWidget {
  const ApiPage({required this.backendUrl,required this.feed,required this.storeDiagnostics,required this.market,required this.onSaved,super.key});
  final String backendUrl;
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
      final result=await FreshApi(widget.backendUrl.trim()).angelStatus();
      if(!mounted)return;
      setState(()=>savedStatus=result);
      if(result['stored_session']==true) {
        setState(()=>message='Saved Angel session found. The app will restore it automatically; enter TOTP only if the session has expired.');
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
      final api=FreshApi(widget.backendUrl.trim());
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
    if(savedStatus['stored_session']==true) Card(child:ListTile(
      leading:const Icon(Icons.verified_user,color:Colors.greenAccent),
      title:const Text('Remembered Angel credentials'),
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
      title:const Text('Remember API Key, Client ID, MPIN and access tokens'),
      subtitle:const Text('Stored encrypted on backend. TOTP is never stored. Turn off to forget saved credentials after this login.'),
      controlAffinity:ListTileControlAffinity.leading,
    ),
    FilledButton.icon(onPressed:working?null:connect,icon:const Icon(Icons.link),label:Text(working?'CONNECTING…':(savedStatus['stored_session']==true?'RESTORE / CONNECT':'CONNECT ANGEL ONE'))),
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
  @override State<AiAccessPage> createState() => _AiAccessState();
}

class _AiAccessState extends State<AiAccessPage> {
  bool working = false;
  bool searchChecking = false;
  String message = 'Cloud AI and search providers are managed by Railway.';
  Map<String, Map<String, dynamic>> searchStatus = const {};

  Future<void> refreshSearchStatus() async {
    if (searchChecking) return;
    setState(() => searchChecking = true);
    try {
      final result = await FreshApi.signal().postJson('/v1/providers/search/status', {});
      final raw = result['providers'];
      final providers = <String, Map<String, dynamic>>{};
      if (raw is Map) {
        for (final name in ['exa', 'tavily']) {
          final value = raw[name];
          if (value is Map) providers[name] = Map<String, dynamic>.from(value);
        }
      }
      if (!mounted) return;
      setState(() {
        searchStatus = providers;
        message = 'Search provider status refreshed from Railway. Provider keys are not stored in this APK.';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        searchStatus = const {
          'exa': {'working': false, 'configured': false, 'evidence_count': 0},
          'tavily': {'working': false, 'configured': false, 'evidence_count': 0},
        };
        message = 'Could not check search providers: ${e.toString().replaceFirst('Exception: ', '')}';
      });
    } finally {
      if (mounted) setState(() => searchChecking = false);
    }
  }

  Future<void> testAI() async {
    if (working) return;
    setState(() => working = true);
    try {
      final result = await FreshApi(widget.backendUrl.trim()).testAIProviders();
      final checks = result['checks'] as List? ?? const [];
      final good = checks.whereType<Map>().where((x) => x['ok'] == true)
          .map((x) => x['provider'].toString()).join(', ');
      final details = checks.whereType<Map>().map((x) {
        final provider = (x['provider'] ?? 'provider').toString();
        if (x['ok'] == true) return '$provider: OK (${x['model'] ?? 'model responded'})';
        return '$provider: FAILED (${x['error'] ?? 'unknown error'})';
      }).join(' | ');
      if (!mounted) return;
      setState(() => message = result['ok'] == true
          ? 'Cloud AI connected: $good. $details'
          : 'NVIDIA connectivity test failed. Check NVIDIA_API_KEY, model access, quota and Railway logs. $details');
    } catch (e) {
      if (mounted) setState(() => message = 'NVIDIA/OpenRouter test failed: ${e.toString().replaceFirst('Exception: ', '')}');
    } finally {
      if (mounted) setState(() => working = false);
    }
  }

  Widget _providerStatusTile(String name) {
    final data = searchStatus[name];
    final workingNow = data?['working'] == true;
    final configured = data?['configured'] == true;
    final color = data == null ? Colors.blueGrey : (workingNow ? Colors.green : Colors.red);
    final label = data == null ? 'CHECK REQUIRED' : (workingNow ? 'WORKING' : (configured ? 'NOT WORKING' : 'NOT CONFIGURED'));
    return Card(child: ListTile(
      leading: Icon(Icons.circle, color: color, size: 15),
      title: Text(name == 'exa' ? 'Exa Search' : 'Tavily Search', style: const TextStyle(fontWeight: FontWeight.w800)),
      subtitle: Text(data == null ? 'Status has not been checked.' : '$label • ${data['evidence_count'] ?? 0} evidence items returned'),
      trailing: Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 11)),
    ));
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(10),
    children: [
      const Section('Cloud AI — Railway Backend'),
      const ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(Icons.cloud_done, color: Colors.cyan),
        title: Text('NVIDIA Cloud Chat'),
        subtitle: Text('NVIDIA is the primary cloud chat provider; OpenRouter is fallback. Configure provider credentials and model settings in Railway Variables. No AI model files are loaded from phone storage.'),
      ),
      FilledButton.icon(
        onPressed: working ? null : testAI,
        icon: const Icon(Icons.psychology),
        label: Text(working ? 'TESTING…' : 'TEST NVIDIA CONNECTION'),
      ),
      const SizedBox(height: 18),
      const Section('News & Evidence Search Status'),
      const Text('Exa and Tavily credentials are managed on Railway. This page checks whether each provider returns evidence; no key fields are needed here.'),
      const SizedBox(height: 8),
      _providerStatusTile('exa'),
      _providerStatusTile('tavily'),
      OutlinedButton.icon(
        onPressed: searchChecking ? null : refreshSearchStatus,
        icon: searchChecking
            ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.refresh),
        label: Text(searchChecking ? 'CHECKING PROVIDERS…' : 'REFRESH EXA / TAVILY STATUS'),
      ),
      const SizedBox(height: 10),
      Text(message),
    ],
  );
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
class InfoRow extends StatelessWidget { const InfoRow(this.left,this.right,{super.key}); final String left,right; @override Widget build(BuildContext context)=>Card(child:ListTile(title:Text(left),trailing:Text(right,style:const TextStyle(fontWeight:FontWeight.w700)))); }
class ChainRow extends StatelessWidget { const ChainRow(this.strike,this.ce,this.pe,{super.key}); final String strike,ce,pe; @override Widget build(BuildContext context)=>Card(child:Row(mainAxisAlignment:MainAxisAlignment.spaceBetween,children:[Padding(padding:const EdgeInsets.all(14),child:Text(ce)),Text(strike,style:const TextStyle(fontWeight:FontWeight.w900)),Padding(padding:const EdgeInsets.all(14),child:Text(pe))])); }
class OIBox extends StatelessWidget { const OIBox(this.title,this.hint,{super.key}); final String title,hint; @override Widget build(BuildContext context)=>Card(child:ListTile(leading:const Icon(Icons.swap_vert),title:Text(title,style:const TextStyle(fontWeight:FontWeight.w800)),subtitle:Text(hint),trailing:const Text('—'))); }
class IndexPicker extends StatelessWidget{
  const IndexPicker({required this.selected,required this.onChanged,super.key});final String selected;final ValueChanged<String> onChanged;
  @override Widget build(BuildContext context)=>DropdownButtonFormField<String>(initialValue:selected,decoration:const InputDecoration(labelText:'Select Index'),items:indexes.map((i)=>DropdownMenuItem(value:i,child:Text(i))).toList(),onChanged:(v){if(v!=null)onChanged(v);});
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
