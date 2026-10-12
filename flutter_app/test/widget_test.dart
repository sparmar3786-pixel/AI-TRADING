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


  testWidgets('Quant Research Hub lists the requested research repositories', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Quant Research Hub'));
    await tester.pumpAndSettle();
    expect(find.text('QUANT RESEARCH HUB'), findsOneWidget);
    final hubScrollable = find.descendant(
      of: find.byType(ListView).last,
      matching: find.byType(Scrollable),
    );
    for (final title in [
      'Awesome Systematic Trading',
      'Awesome Algorithmic Trading',
      'Awesome Quant',
      'Awesome Deep Trading',
      'Stock Market Dashboard',
      'AI Stock Market Dashboard',
    ]) {
      final item = find.text(title);
      await tester.scrollUntilVisible(item, 250, scrollable: hubScrollable);
      expect(item, findsOneWidget);
    }
  });

  testWidgets('additional broker-home prototype uses Angel One-backed market data', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Broker Home (Prototype)'));
    await tester.pumpAndSettle();
    expect(find.text('Invest'), findsOneWidget);
    expect(find.text('INDIAN MARKET WATCH'), findsOneWidget);
    expect(find.text('Markets, watchlist & account overview'), findsOneWidget);
  });

  testWidgets('PDF report tab includes all report pages, screenshot index and repository links', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('PDF Report & Repositories'));
    await tester.pumpAndSettle();
    expect(find.text('PDF REPORT • ALL 10 PAGES & FIX CHECKLIST'), findsOneWidget);
    expect(find.textContaining('PDF Page 1'), findsOneWidget);
    final reportScrollable = find.descendant(
      of: find.byType(ListView).last,
      matching: find.byType(Scrollable),
    );
    final pageTen = find.textContaining('PDF Page 10');
    await tester.scrollUntilVisible(pageTen, 300, scrollable: reportScrollable);
    expect(pageTen, findsOneWidget);
    final screenshotIndex = find.text('ALL 15 SCREENSHOT INDEX');
    await tester.scrollUntilVisible(screenshotIndex, 300, scrollable: reportScrollable);
    expect(screenshotIndex, findsOneWidget);
    final repositoryLinks = find.text('REPOSITORY & DOCUMENTATION LINKS');
    await tester.scrollUntilVisible(repositoryLinks, 300, scrollable: reportScrollable);
    expect(repositoryLinks, findsOneWidget);
    final priorityRootCause = find.text('PRIORITY ROOT CAUSE');
    await tester.drag(reportScrollable, const Offset(0, 3000));
    await tester.pumpAndSettle();
    expect(priorityRootCause, findsOneWidget);
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

  testWidgets('Research Engines shows live data and non-chart research sources', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    DefaultTabController.of(tabBarContext).animateTo(tabs.indexOf('Research Engines'));
    await tester.pumpAndSettle();
    expect(find.text('RESEARCH ENGINES • LIVE BACKEND OUTPUT'), findsOneWidget);
    expect(find.text('TECHNICAL INDICATOR ENGINE'), findsOneWidget);
    expect(find.text('OPTIONS / OPEN INTEREST ENGINE'), findsOneWidget);
    final researchScrollable = find.descendant(
      of: find.byType(ListView).last,
      matching: find.byType(Scrollable),
    );
    final researchSources = find.text('RESEARCH SOURCES • NON-CHART REPOSITORIES');
    await tester.scrollUntilVisible(researchSources, 250, scrollable: researchScrollable);
    expect(researchSources, findsOneWidget);
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
    final repositoryLibrary = find.byKey(const ValueKey('drawer-tab-Repository Library'));
    await tester.scrollUntilVisible(repositoryLibrary, 250, scrollable: drawerScrollable);
    expect(repositoryLibrary, findsOneWidget);
    await tester.scrollUntilVisible(apiRailway, 250, scrollable: drawerScrollable);
    await tester.tap(apiRailway);
    await tester.pumpAndSettle();
    expect(find.text('ADVANCED API + RAILWAY CONNECTION'), findsOneWidget);
    expect(find.text('Railway FastAPI starter'), findsOneWidget);
  });

  testWidgets('Trading Setup shows Angel One architecture and research links', (tester) async {
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
    final engineScrollable = find.descendant(
      of: find.byType(ListView).last,
      matching: find.byType(Scrollable),
    );
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
