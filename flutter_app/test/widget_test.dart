import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';

void main() {
  test('removed Strategy and Quant tabs are absent from APK navigation model', () {
    expect(tabs, contains('Dashboard'));
    expect(tabs, contains('Market'));
    expect(tabs, contains('Signals'));
    expect(tabs, contains('API'));
    expect(tabs, isNot(contains('Strategies')));
    expect(tabs, isNot(contains('Strategy Library')));
    expect(tabs, isNot(contains('Quant Engine')));
    expect(tabs, isNot(contains('Quant Signal')));
    expect(tabs, isNot(contains('Strategy Signal')));
  });

  testWidgets('app shell renders navigation without Strategy or Quant Engine screens', (tester) async {
    await tester.pumpWidget(const FreshApp());
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byKey(const ValueKey('open-navigation-menu')), findsOneWidget);
    expect(find.text('Strategies'), findsNothing);
    expect(find.text('Quant Engine'), findsNothing);
    expect(find.text('Quant Signal'), findsNothing);
    expect(find.text('Strategy Signal'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('open-navigation-menu')));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Strategies'), findsNothing);
    expect(find.text('Quant Engine'), findsNothing);
  });
}
