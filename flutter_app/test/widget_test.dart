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
    expect(tabs, contains('API'));
    expect(tabs, contains('AI Access'));
    expect(tabs, isNot(contains('Repository Library')));
    expect(tabs, isNot(contains('Quant Research Hub')));
    expect(tabs, isNot(contains('Quant & Trading Repositories')));
    expect(tabs, contains('PDF Reports'));
    expect(find.byKey(const ValueKey('open-navigation-menu')), findsOneWidget);
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
}

