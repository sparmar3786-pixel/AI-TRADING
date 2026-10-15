import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';

void main() {
  testWidgets('AI Trading app starts and exposes core market/API tabs', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.pump(const Duration(milliseconds: 100));

    expect(tabs, contains('Dashboard'));
    expect(tabs, contains('Market'));
    expect(tabs, contains('Signals'));
    expect(tabs, contains('Strategy Library'));
    expect(tabs, contains('API'));
    expect(tabs, contains('AI Access'));
    expect(tabs, isNot(contains('Repository Library')));
    expect(tabs, isNot(contains('Quant Research Hub')));
    expect(tabs, isNot(contains('Quant & Trading Repositories')));
    expect(tabs, isNot(contains('PDF Reports')));
    expect(tabs, isNot(contains('AI Chat')));
    expect(find.byKey(const ValueKey('open-navigation-menu')), findsOneWidget);
  });


  testWidgets('Strategy Library exposes inventory without claiming live readiness', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Strategy Library').last);
    await tester.pumpAndSettle();

    expect(find.text('STRATEGY LIBRARY'), findsOneWidget);
    expect(find.text('OI Price Action'), findsOneWidget);
    expect(find.text('Hero Zero'), findsOneWidget);
    expect(find.text('Failed-Move / PDH-PDL'), findsOneWidget);
    expect(find.text('EMA Crossover'), findsOneWidget);
    expect(find.text('DAY-HL Liquidity Sweep'), findsOneWidget);
    expect(find.text('Opening Range Breakout (ORB)'), findsOneWidget);
    expect(find.text('VWAP Strategy'), findsOneWidget);
    expect(find.text('Live API wiring not verified'), findsWidgets);
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
  testWidgets('AI Access is cloud-only with no on-device model controls', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('AI Access').last);
    await tester.pumpAndSettle();

    expect(find.text('ADD OFFLINE GGUF MODELS'), findsNothing);
    expect(find.text('TEST ALL OFFLINE MODELS'), findsNothing);
    expect(find.text('Offline AI — On-device GGUF Models'), findsNothing);
    expect(find.text('OPEN AI CHAT • LOAD SELECTED OFFLINE MODEL'), findsNothing);
  });

}

