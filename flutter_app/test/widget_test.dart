import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';
import 'package:ai_trading_signal/risk_calculator_page.dart';

void main() {
  testWidgets('Risk calculator follows parent selection from an index to an MCX contract', (tester) async {
    const market = <String, dynamic>{
      'NIFTY': <String, dynamic>{'ltp': 25000, 'age_seconds': 2, 'live': true, 'lot_size': 25},
    };
    const commodities = <dynamic>[
      <String, dynamic>{'name': 'CRUDEOIL', 'symbol': 'CRUDEOIL', 'ltp': 6200, 'age_seconds': 2, 'live': true, 'lot_size': 100},
    ];

    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: RiskCalculator(selectedIndex: 'NIFTY', marketByIndex: market, commodities: commodities),
        ),
      ),
    ));
    expect(find.text('NIFTY'), findsOneWidget);

    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: RiskCalculator(selectedIndex: 'CRUDEOIL', marketByIndex: market, commodities: commodities),
        ),
      ),
    ));
    await tester.pump();

    expect(find.text('CRUDEOIL'), findsOneWidget);
    expect(find.text('LTP: ₹6200.00'), findsOneWidget);
    expect(find.text('LTP: ₹25000.00'), findsNothing);
  });

  testWidgets('Fresh app renders all top-level tabs', (tester) async {
    await tester.pumpWidget(const FreshApp());

    for (final tab in tabs) {
      expect(find.text(tab), findsAtLeastNWidgets(1));
    }
    expect(find.text('Paper Trades'), findsNothing);
    expect(tabs, contains('Strategies'));
    expect(tabs, contains('Quant Engine'));
    expect(tabs, contains('Strategy Signal'));
    expect(tabs, contains('Quant Signal'));
    expect(tabs, contains('Signal Calendar'));
    expect(tabs, isNot(contains('Research Engines')));
    expect(tabs, isNot(contains('API & Railway')));
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

  testWidgets('Strategy Signal tab is available without legacy ResearchEnginesPage', (tester) async {
    await tester.pumpWidget(const FreshApp());
    expect(tabs, contains('Strategy Signal'));
    expect(tabs, contains('Quant Signal'));
    expect(tabs, contains('Signal Calendar'));
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
