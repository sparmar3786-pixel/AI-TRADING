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
