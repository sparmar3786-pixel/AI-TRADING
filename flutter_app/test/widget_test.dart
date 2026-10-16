import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';

void main() {
  testWidgets('Trading app starts with strategy tab and no AI tabs', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

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
    // Tall surface so every strategy card is laid out without relying on
    // scrollUntilVisible (flaky against TabBar horizontal Scrollables in CI).
    await tester.binding.setSurfaceSize(const Size(800, 4000));
    addTearDown(() async {
      await tester.binding.setSurfaceSize(null);
    });

    await tester.pumpWidget(const FreshApp());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // Instant tab switch — avoid animateTo + pumpAndSettle (refresh timer).
    final tabController = DefaultTabController.of(
      tester.element(find.byType(TabBar)),
    );
    tabController.index = tabs.indexOf('Strategies');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('STRATEGY LIBRARY'), findsOneWidget);
    expect(find.byKey(const ValueKey('strategy-library-list')), findsOneWidget);

    const strategyLabels = <String>[
      'OI Price Action',
      'Hero Zero',
      'Failed-Move / PDH-PDL',
      'EMA Crossover',
      'DAY-HL Liquidity Sweep',
      'Opening Range Breakout (ORB)',
      'VWAP Strategy',
    ];
    for (final label in strategyLabels) {
      expect(
        find.text(label),
        findsOneWidget,
        reason: 'Missing strategy card: $label',
      );
    }

    // Present on multiple SOURCE BUNDLED cards (e.g. OI Price Action).
    expect(
      find.textContaining('Live API wiring not verified'),
      findsWidgets,
      reason: 'Strategy cards must disclose that live API wiring is unverified',
    );
  });

  testWidgets('SMC, MCX and Order Flow chart pages are completely absent', (tester) async {
    const removedLabels = <String>[
      'SMC Pro Chart',
      'SMC Chart',
      'Smart Money Concepts Chart',
      'Order Flow & Footprint',
      'Order Flow Chart',
      'Footprint Chart',
      'FOOTPRINT CHART',
      'MCX',
      'MCX Commodities',
      'MCX Commodity Exchange',
      'Commodities',
      'CRUDEOIL',
      'NATURALGAS',
    ];
    for (final tab in tabs) {
      expect(
        removedLabels.map((label) => label.toLowerCase()),
        isNot(contains(tab.toLowerCase())),
        reason: 'Removed chart page must not be a top-level tab: $tab',
      );
    }

    await tester.pumpWidget(const FreshApp());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    for (final label in removedLabels) {
      expect(find.text(label), findsNothing, reason: '$label must not be visible');
    }

    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    for (final label in removedLabels) {
      expect(
        find.text(label),
        findsNothing,
        reason: '$label must not appear in navigation',
      );
    }
  });
}
