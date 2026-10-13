import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';

void main() {
  testWidgets('Fresh app renders all top-level tabs', (tester) async {
    await tester.pumpWidget(const FreshApp());

    for (final tab in tabs) {
      expect(find.text(tab), findsAtLeastNWidgets(1));
    }
    expect(find.text('Paper Trades'), findsNothing);
    expect(tabs, contains('Research Engines'));
  });


  testWidgets('Broker Home uses Angel One-backed market data', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Broker Home'));
    await tester.pumpAndSettle();
    expect(find.text('Invest'), findsOneWidget);
    expect(find.text('INDIAN MARKET WATCH'), findsOneWidget);
    expect(find.text('Markets, watchlist & account overview'), findsOneWidget);
  });

  // Keep this regression guard: selecting a removed tab caused TabController.index < 0 in CI.
  testWidgets('non-functional PDF report tab is removed until real export exists', (tester) async {
    await tester.pumpWidget(const FreshApp());
    expect(tabs.contains('PDF Report & Fixes'), isFalse);
    expect(find.text('PDF REPORT • PAGE-BY-PAGE ERROR & FIX CHECKLIST'), findsNothing);
  });

  testWidgets('pro option chain renders quote table controls', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Option Chain'));
    await tester.pumpAndSettle();
    expect(find.text('PRO OPTION CHAIN'), findsOneWidget);
    expect(find.text('CALL OI'), findsOneWidget);
    expect(find.text('PUT OI'), findsOneWidget);
    expect(find.text('CALL + PUT'), findsOneWidget);
  });

  testWidgets('Data Health hides raw feed and normalized-store diagnostics', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Data Health'));
    await tester.pumpAndSettle();
    expect(find.text('DATA HEALTH & CONNECTION STATUS'), findsOneWidget);
    // Assert the visible health header and ensure implementation-only raw
    // diagnostics are not exposed as a user-facing section.
    expect(find.text('Feed diagnostics'), findsNothing);
    expect(find.text('Normalized store diagnostics'), findsNothing);
  });

  testWidgets('Quant Engine Lab exposes all five research capabilities', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Quant Engine Lab'));
    await tester.pumpAndSettle();
    expect(find.text('QUANT ENGINE LAB'), findsOneWidget);
    expect(find.text('1. Streaming vs offline research'), findsOneWidget);
    // The diagnostics added to the first card make the AI section lower on
    // small screens. Scroll the ListView rather than assuming it is on-screen.
    final labScrollable = find.descendant(
      of: find.byType(ListView).last,
      matching: find.byType(Scrollable),
    ).first;
    final sentimentHeading = find.text('2. AI news sentiment + reasoning');
    await tester.scrollUntilVisible(sentimentHeading, 250, scrollable: labScrollable);
    expect(sentimentHeading, findsOneWidget);
    final sentimentButton = find.text('Analyze sentiment with AI');
    await tester.scrollUntilVisible(sentimentButton, 250, scrollable: labScrollable);
    expect(sentimentButton, findsOneWidget);
    expect(tabs, contains('Quant Engine Lab'));
  });

  testWidgets('historical backtest runs from a configurable UI, not an empty hardcoded sample', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Backtesting'));
    await tester.pumpAndSettle();
    expect(find.text('HISTORICAL STRATEGY BACKTEST'), findsOneWidget);
    expect(find.text('RUN HISTORICAL BACKTEST'), findsOneWidget);
    expect(find.textContaining('Angel One historical index candles'), findsOneWidget);
    expect(find.text('PAPER TRADING'), findsNothing);
  });

  testWidgets('Research Engines shows live validation outputs without repository links', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Research Engines'));
    await tester.pumpAndSettle();
    expect(find.text('RESEARCH ENGINES • LIVE BACKEND OUTPUT'), findsOneWidget);
    expect(find.text('TECHNICAL INDICATOR ENGINE'), findsOneWidget);
    expect(find.text('OPTIONS / OPEN INTEREST ENGINE'), findsOneWidget);
    expect(find.textContaining('github.com'), findsNothing);
    expect(find.text('VALIDATION PERFORMANCE'), findsNothing);
  });

  testWidgets('Research Engines exposes MCX snapshot and keeps commodity CE PE gated', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ResearchEnginesPage(
          market: const {},
          signals: const {},
          ai: const {},
          commodities: const [
            {
              'name': 'CRUDEOIL',
              'symbol': 'CRUDEOIL26OCTFUT',
              'live': true,
              'ltp': 5500.0,
              'decision': 'WAIT',
              'candidate_decision': 'WAIT',
              'indicators': {'ema_fast': 5501.0, 'ema_slow': 5498.0},
            },
          ],
          optionChains: const {
            'CRUDEOIL': [
              {'side': 'CE', 'strike': 5500.0, 'oi': 10},
              {'side': 'PE', 'strike': 5500.0, 'oi': 20},
            ],
          },
          lastFetch: 'test snapshot',
          selectedIndex: 'CRUDEOIL',
          onIndexChanged: (_) {},
        ),
      ),
    ));

    expect(find.text('TECHNICAL INDICATOR ENGINE'), findsOneWidget);
    expect(find.text('OPTIONS / OPEN INTEREST ENGINE'), findsOneWidget);
    expect(find.text('MCX CE quotes'), findsOneWidget);
    expect(find.text('MCX PE quotes'), findsOneWidget);
    expect(find.text('WAIT'), findsWidgets);
    expect(find.textContaining('Commodity CE/PE entries remain blocked'), findsOneWidget);
    expect(find.textContaining('5500.00'), findsWidgets);
  });

  testWidgets('hamburger drawer exposes API and Railway navigation', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pumpAndSettle();

    final drawerScrollable = find.descendant(
      of: find.byType(Drawer),
      matching: find.byType(Scrollable),
    );
    final apiRailway = find.byKey(const ValueKey('drawer-tab-API & Railway'));
    await tester.scrollUntilVisible(apiRailway, 250, scrollable: drawerScrollable);
    expect(apiRailway, findsOneWidget);
    final dataHealth = find.byKey(const ValueKey('drawer-tab-Data Health'));
    await tester.scrollUntilVisible(dataHealth, 250, scrollable: drawerScrollable);
    expect(dataHealth, findsOneWidget);
    final repositoryLibrary = find.byKey(const ValueKey('drawer-tab-Market Diagnostics'));
    await tester.scrollUntilVisible(repositoryLibrary, 250, scrollable: drawerScrollable);
    expect(repositoryLibrary, findsOneWidget);
    await tester.scrollUntilVisible(apiRailway, 250, scrollable: drawerScrollable);
    await tester.tap(apiRailway);
    await tester.pumpAndSettle();
    expect(find.text('ADVANCED API + RAILWAY CONNECTION'), findsOneWidget);
    expect(find.text('Secret handling'), findsOneWidget);
    expect(find.textContaining('github.com'), findsNothing);
  });

  testWidgets('Trading Setup shows Angel One architecture without repository links', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.tap(find.byTooltip('Open navigation menu'));
    await tester.pumpAndSettle();
    final drawerScrollable = find.descendant(
      of: find.byType(Drawer),
      matching: find.byType(Scrollable),
    );
    final tradingSetup = find.byKey(const ValueKey('drawer-tab-Trading Setup'));
    await tester.scrollUntilVisible(tradingSetup, 250, scrollable: drawerScrollable);
    await tester.tap(tradingSetup);
    await tester.pumpAndSettle();

    expect(find.text('COMPLETE TRADING SYSTEM • ANGEL ONE EDITION'), findsOneWidget);
    final setupScrollable = find.descendant(
      of: find.byType(ListView).last,
      matching: find.byType(Scrollable),
    );
    final brokerChoice = find.text('Broker choice: Angel One SmartAPI. No Zerodha/Kite integration is required for this app.');
    await tester.scrollUntilVisible(brokerChoice, 250, scrollable: setupScrollable);
    expect(brokerChoice, findsOneWidget);
    final systemFlow = find.text('SYSTEM FLOW');
    await tester.scrollUntilVisible(systemFlow, 250, scrollable: setupScrollable);
    expect(systemFlow, findsOneWidget);
    expect(find.textContaining('github.com'), findsNothing);
  });

  testWidgets('5-Layer Quant Signal Engine shows signal, validation and monitoring layers', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pumpAndSettle();
    final drawerScrollable = find.descendant(
      of: find.byType(Drawer),
      matching: find.byType(Scrollable),
    );
    final engineTab = find.byKey(const ValueKey('drawer-tab-5-Layer Quant Signal Engine'));
    await tester.scrollUntilVisible(engineTab, 250, scrollable: drawerScrollable);
    await tester.tap(engineTab);
    await tester.pumpAndSettle();

    expect(find.text('TRADE ENGINE'), findsOneWidget);
    expect(find.text('SIGNAL ENGINE'), findsOneWidget);
    final engineList = find.byKey(const ValueKey('trade-engine-primary-list'));
    expect(engineList, findsOneWidget);
    final engineScrollable = find.descendant(
      of: engineList,
      matching: find.byType(Scrollable),
    );
    expect(engineScrollable, findsOneWidget);
    final riskLayer = find.text('RISK & 10-MINUTE STABILITY');
    await tester.scrollUntilVisible(riskLayer, 250, scrollable: engineScrollable);
    expect(riskLayer, findsOneWidget);
    final monitorLayer = find.text('READ-ONLY BROKER MONITOR');
    await tester.scrollUntilVisible(monitorLayer, 250, scrollable: engineScrollable);
    expect(monitorLayer, findsOneWidget);
    final orderBookButton = find.text('LOAD / REFRESH ANGEL ONE ORDER BOOK');
    await tester.scrollUntilVisible(orderBookButton, 250, scrollable: engineScrollable);
    expect(orderBookButton, findsOneWidget);
  });

  testWidgets('Flow Monitor exposes measured API and provider validation telemetry', (tester) async {
    await tester.pumpWidget(const FreshApp());

    final tabBar = find.byType(TabBar).first;
    final tabBarContext = tester.element(tabBar);
    final controller = DefaultTabController.of(tabBarContext);
    controller.animateTo(tabs.indexOf('Flow Monitor'));

    // Advance the tab transition deterministically. Do not wait for the
    // periodic diagnostics timer or live HTTP calls to settle.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pump();

    expect(controller.index, tabs.indexOf('Flow Monitor'));
    expect(find.textContaining('FLOW MONITOR'), findsOneWidget);

    final monitorScrollable = find.descendant(
      of: find.byType(RefreshIndicator),
      matching: find.byType(Scrollable),
    ).first;
    await tester.scrollUntilVisible(
      find.text('SERVER API ROUTE METRICS'),
      250,
      scrollable: monitorScrollable,
    );
    expect(find.text('SERVER API ROUTE METRICS'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.text('GEMINI + OPENAI + OPENROUTER DATA VALIDATION'),
      250,
      scrollable: monitorScrollable,
    );
    expect(find.text('GEMINI + OPENAI + OPENROUTER DATA VALIDATION'), findsOneWidget);
    expect(find.text('TEST GEMINI + OPENAI + OPENROUTER'), findsOneWidget);

    // Dispose Flow Monitor first so its periodic poll is cancelled, then let
    // outstanding Future.timeout timers finish. This tests real cleanup rather
    // than leaving pending fake timers behind at test teardown.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 13));
  });

  testWidgets('Pro chart clearly reports missing candles instead of fabricating data', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ProCandlestickChart(index: 'NIFTY', market: {}, signal: {}),
        ),
      ),
    );

    expect(find.text('PRO CHART'), findsOneWidget);
    expect(find.text('Waiting for real candle history'), findsOneWidget);
    expect(find.text('No synthetic candles are displayed'), findsOneWidget);
  });
}
