import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';
import 'package:ai_trading_signal/risk_calculator_page.dart';

void main() {
  testWidgets('Risk calculator accepts index and commodity selections', (tester) async {
    const market = <String, dynamic>{
      'NIFTY': <String, dynamic>{
        'ltp': 25000,
        'age_seconds': 2,
        'live': true,
        'lot_size': 25,
      },
    };
    const commodities = <dynamic>[
      <String, dynamic>{
        'name': 'CRUDEOIL',
        'symbol': 'CRUDEOIL',
        'ltp': 6200,
        'age_seconds': 2,
        'live': true,
        'lot_size': 100,
      },
    ];

    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: RiskCalculator(
            selectedIndex: 'NIFTY',
            marketByIndex: market,
            commodities: commodities,
          ),
        ),
      ),
    ));
    expect(find.text('NIFTY'), findsOneWidget);

    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: RiskCalculator(
            selectedIndex: 'CRUDEOIL',
            marketByIndex: market,
            commodities: commodities,
          ),
        ),
      ),
    ));
    await tester.pump();
    expect(find.text('CRUDEOIL'), findsOneWidget);
    expect(find.text('LTP: ₹6200.00'), findsOneWidget);
    expect(find.text('LTP: ₹25000.00'), findsNothing);
  });

  testWidgets('Fresh app exposes the current signal and strategy tabs', (tester) async {
    await tester.pumpWidget(const FreshApp());

    for (final tab in tabs) {
      expect(find.text(tab), findsAtLeastNWidgets(1), reason: 'Missing tab: $tab');
    }

    expect(tabs, contains('Quant Signal'));
    expect(tabs, contains('Strategy Signal'));
    expect(tabs, contains('Signal Calendar'));
    expect(tabs, contains('Strategies'));
    expect(tabs, contains('Backtesting'));

    // Legacy names removed during the navigation cleanup must not be required
    // by tests or used to calculate a TabController index.
    expect(tabs, isNot(contains('Research Engines')));
    expect(tabs, isNot(contains('Quant Engine Lab')));
    expect(tabs, isNot(contains('Flow Monitor')));
    expect(tabs, isNot(contains('Trading Setup')));
    expect(tabs, isNot(contains('PDF Report & Fixes')));
  });

  testWidgets('Signal calendar and dedicated signal screens are reachable', (tester) async {
    await tester.pumpWidget(const FreshApp());
    final tabBarContext = tester.element(find.byType(TabBar).first);
    final controller = DefaultTabController.of(tabBarContext);

    controller.animateTo(tabs.indexOf('Quant Signal'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(controller.index, tabs.indexOf('Quant Signal'));

    controller.animateTo(tabs.indexOf('Strategy Signal'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(controller.index, tabs.indexOf('Strategy Signal'));

    controller.animateTo(tabs.indexOf('Signal Calendar'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(controller.index, tabs.indexOf('Signal Calendar'));
  });

  testWidgets('Pro chart reports missing candles instead of fabricating data', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: ProCandlestickChart(index: 'NIFTY', market: {}, signal: {}),
      ),
    ));

    expect(find.text('PRO CHART'), findsOneWidget);
    expect(find.text('Waiting for real candle history'), findsOneWidget);
    expect(find.text('No synthetic candles are displayed'), findsOneWidget);
  });
}
