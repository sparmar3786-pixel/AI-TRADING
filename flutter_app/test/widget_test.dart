import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';
import 'package:ai_trading_signal/strategy_library_page.dart';

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
    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pumpAndSettle();
    final drawerScroll = find.descendant(of: find.byType(Drawer), matching: find.byType(Scrollable)).first;
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('drawer-tab-Strategies')),
      250,
      scrollable: drawerScroll,
    );
    await tester.tap(find.byKey(const ValueKey('drawer-tab-Strategies')));
    await tester.pumpAndSettle();

    expect(find.text('STRATEGY LIBRARY'), findsOneWidget);
    final strategyScroll = find.descendant(
      of: find.byType(StrategyLibraryPage),
      matching: find.byType(Scrollable),
    ).first;
    for (final label in <String>[
      'OI Price Action',
      'Hero Zero',
      'Failed-Move / PDH-PDL',
      'EMA Crossover',
      'DAY-HL Liquidity Sweep',
      'Opening Range Breakout (ORB)',
      'VWAP Strategy',
    ]) {
      await tester.scrollUntilVisible(find.text(label), 250, scrollable: strategyScroll);
      expect(find.text(label), findsOneWidget, reason: '$label must be in the Strategies tab');
    }
    await tester.scrollUntilVisible(
      find.text('Live API wiring not verified'),
      250,
      scrollable: strategyScroll,
    );
    expect(find.text('Live API wiring not verified'), findsWidgets);
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
