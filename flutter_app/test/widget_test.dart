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

    // Target the Strategy Library's own vertical Scrollable. The ListView
    // lazily builds off-screen children, so assertions must scroll this exact
    // list rather than a horizontal TabBar scrollable.
    final strategyList = find.byKey(const ValueKey('strategy-library-list'));
    expect(strategyList, findsOneWidget);
    final strategyScrollable = find.descendant(
      of: strategyList,
      matching: find.byType(Scrollable),
    );
    expect(strategyScrollable, findsOneWidget);

    final strategyLabels = <String>[
      'OI Price Action',
      'Hero Zero',
      'Failed-Move / PDH-PDL',
      'EMA Crossover',
      'DAY-HL Liquidity Sweep',
      'Opening Range Breakout (ORB)',
      'VWAP Strategy',
    ];
    for (final label in strategyLabels) {
      final labelFinder = find.text(label);
      if (labelFinder.evaluate().isEmpty) {
        await tester.scrollUntilVisible(
          labelFinder,
          250,
          scrollable: strategyScrollable,
        );
        await tester.pumpAndSettle();
      }
      expect(labelFinder, findsOneWidget, reason: 'Missing strategy card: $label');
    }

    final disclaimer = find.textContaining('Live API wiring not verified');
    if (disclaimer.evaluate().isEmpty) {
      await tester.scrollUntilVisible(
        disclaimer,
        250,
        scrollable: strategyScrollable,
      );
      await tester.pumpAndSettle();
    }
    expect(
      disclaimer,
      findsWidgets,
      reason: 'Strategy cards must disclose that live API wiring is unverified',
    );
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
