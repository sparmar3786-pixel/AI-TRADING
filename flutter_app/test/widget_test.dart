import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';

void main() {
  testWidgets('Trading app starts with strategy tab and no AI tabs', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.pump(const Duration(milliseconds: 100));

    expect(tabs, contains('Dashboard'));
    expect(tabs, contains('Market'));
    expect(tabs, contains('Signals'));
    expect(tabs, contains('Parmar'));
    expect(tabs, contains('API'));
    expect(tabs, isNot(contains('AI Access')));
    expect(tabs, isNot(contains('AI Chat')));
    expect(tabs, isNot(contains('Quant Engine Lab')));
    expect(tabs, isNot(contains('Research Engines')));
    expect(tabs, isNot(contains('5-Layer Quant Signal Engine')));
    expect(find.byKey(const ValueKey('open-navigation-menu')), findsOneWidget);
  });

  testWidgets('Parmar tab lists all known engines and discloses integration limits', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pumpAndSettle();
    final drawerScroll = find.descendant(of: find.byType(Drawer), matching: find.byType(Scrollable)).first;
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('drawer-tab-Parmar')),
      250,
      scrollable: drawerScroll,
    );
    await tester.tap(find.byKey(const ValueKey('drawer-tab-Parmar')));
    await tester.pumpAndSettle();

    expect(find.text('PARMAR STRATEGY ENGINE'), findsOneWidget);

    // Use the keyed ListView itself for deterministic gestures. Flutter's
    // scrollUntilVisible/dragUntilVisible resolves its scrollable with .single,
    // which has been brittle with nested Material scrollables in this screen.
    final strategyList = find.byKey(const ValueKey('strategy-library-list'));
    final finalStrategyCard = find.byKey(const ValueKey('strategy-card-vwap'));
    expect(strategyList, findsOneWidget);
    for (var attempt = 0; attempt < 20 && finalStrategyCard.evaluate().isEmpty; attempt++) {
      await tester.drag(strategyList, const Offset(0, -250));
      await tester.pumpAndSettle();
    }
    expect(finalStrategyCard, findsOneWidget);

    // This is a local inventory/status disclosure, not proof of live API
    // connectivity. Keep the test independent from the real backend response.
    expect(find.text('Not active; indicator does not prove entry/exit integration'), findsOneWidget);
  });

  testWidgets('SMC, MCX and Order Flow chart pages are completely absent', (tester) async {
    const removedLabels = <String>[
      'SMC Pro Chart', 'SMC Chart', 'Smart Money Concepts Chart',
      'Order Flow & Footprint', 'Order Flow Chart', 'Footprint Chart',
      'FOOTPRINT CHART', 'MCX', 'MCX Commodities', 'MCX Commodity Exchange',
      'Commodities', 'CRUDEOIL', 'NATURALGAS',
    ];
    for (final tab in tabs) {
      expect(removedLabels.map((label) => label.toLowerCase()),
        isNot(contains(tab.toLowerCase())),
        reason: 'Removed chart page must not be a top-level tab: $tab');
    }
    await tester.pumpWidget(const FreshApp());
    await tester.pump(const Duration(milliseconds: 100));
    for (final label in removedLabels) {
      expect(find.text(label), findsNothing, reason: '$label must not be visible');
    }
    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pumpAndSettle();
    for (final label in removedLabels) {
      expect(find.text(label), findsNothing, reason: '$label must not appear in navigation');
    }
  });
  testWidgets('Indicators page clearly fixes the live signal EMA periods', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: IndicatorsPage(
          selected: 'NIFTY',
          signal: <String, dynamic>{
            'indicators': <String, dynamic>{
              'ema_fast': 101.0,
              'ema_slow': 99.0,
            },
          },
          onIndex: (_) {},
        ),
      ),
    ));
    expect(find.text('Core EMA Configuration'), findsOneWidget);
    expect(find.text('Live signal EMA fast period'), findsOneWidget);
    expect(find.text('8', skipOffstage: false), findsOneWidget);
    expect(find.text('21', skipOffstage: false), findsOneWidget);
    expect(find.text('APPLY EMA'), findsNothing);
    expect(find.byType(TextField), findsNothing);
  });

}
