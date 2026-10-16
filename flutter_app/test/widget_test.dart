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
    expect(tabs, contains('Strategies'));
    expect(tabs, contains('API'));
    expect(tabs, isNot(contains('AI Access')));
    expect(tabs, isNot(contains('AI Chat')));
    expect(tabs, isNot(contains('Quant Engine Lab')));
    expect(tabs, isNot(contains('Research Engines')));
    expect(tabs, isNot(contains('5-Layer Quant Signal Engine')));
    expect(find.byKey(const ValueKey('open-navigation-menu')), findsOneWidget);
  });

  testWidgets('Strategies tab lists all known engines and discloses integration limits', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.pump(const Duration(milliseconds: 100));
    // Select the Strategies tab through its controller. The horizontal TabBar
    // can place its text off-screen in the 800x600 CI test viewport, so tapping
    // a matching Text('Strategies') may hit the off-screen app-bar tab instead
    // of the drawer item.
    final tabController = DefaultTabController.of(
      tester.element(find.byType(TabBar)),
    );
    tabController.animateTo(tabs.indexOf('Strategies'));
    await tester.pumpAndSettle();

    expect(find.text('STRATEGY LIBRARY'), findsOneWidget);

    // ListView builds rows lazily. Scroll each strategy card into the viewport
    // before asserting its text; otherwise off-screen cards do not exist in the
    // widget tree yet and the test fails even though the library contains them.
    final strategyLabels = <String>[
      'OI Price Action',
      'Hero Zero',
      'Failed-Move / PDH-PDL',
      'EMA Crossover',
      'DAY-HL Liquidity Sweep',
      'Opening Range Breakout (ORB)',
      'VWAP Strategy',
    ];
    final verticalScrollable = find.byType(Scrollable).last;
    for (final label in strategyLabels) {
      await tester.scrollUntilVisible(
        find.text(label),
        250,
        scrollable: verticalScrollable,
      );
      await tester.pumpAndSettle();
      expect(find.text(label), findsOneWidget, reason: 'Missing strategy card: $label');
    }
    // The integration disclaimer is inside lazily built cards too; bring one
    // into view before asserting it exists in the rendered widget tree.
    await tester.scrollUntilVisible(
      find.textContaining('Live API wiring not verified'),
      250,
      scrollable: verticalScrollable,
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Live API wiring not verified'), findsWidgets);
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
}
