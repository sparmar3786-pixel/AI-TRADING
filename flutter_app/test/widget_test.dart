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
      final labelFinder = (label == 'Opening Range Breakout (ORB)' || label == 'VWAP Strategy')
          ? find.text(label).last
          : find.text(label);
      await tester.scrollUntilVisible(labelFinder, 250, scrollable: strategyScroll);
      expect(labelFinder, findsOneWidget, reason: '$label must be in the Strategies tab');
    }
    final liveStatus = find.text('Live API wiring not verified').first;
    await tester.scrollUntilVisible(liveStatus, 250, scrollable: strategyScroll);
    expect(liveStatus, findsOneWidget);
  });

  testWidgets('Strategy Library shows ORB/VWAP backend candidates but keeps them non-actionable', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: StrategyLibraryPage(
        selectedIndex: 'NIFTY',
        signals: {
          'NIFTY': {
            'strategy_candidates': {
              'orb': {
                'candidate_decision': 'CALL BUY',
                'decision': 'WAIT',
                'entry': 25000.0,
                'stop_loss': 24900.0,
                'target': 25200.0,
                'data_fresh': true,
                'reasons': ['Opening range breakout confirmed'],
                'guards': ['OPTION_CONTRACT_MAPPING_REQUIRED'],
                'live_validation': {
                  'verdict': 'PENDING',
                  'blocks': ['Five-layer quant validation required'],
                },
              },
              'vwap': {
                'decision': 'WAIT',
                'data_fresh': false,
                'reasons': ['No confirmed VWAP cross'],
                'guards': ['NO_VALID_SETUP'],
                'live_validation': {'verdict': 'FAIL', 'blocks': []},
              },
            },
          },
        },
      ),
    ));
    await tester.pumpAndSettle();
    final strategyScroll = find.descendant(
      of: find.byType(StrategyLibraryPage),
      matching: find.byType(Scrollable),
    ).first;
    await tester.scrollUntilVisible(
      find.text('Opening Range Breakout (ORB)').first,
      250,
      scrollable: strategyScroll,
    );
    expect(find.text('Candidate: CALL BUY • Approved decision: WAIT'), findsOneWidget);
    expect(find.textContaining('Underlying entry: 25000.0 • SL: 24900.0 • Target: 25200.0'), findsOneWidget);
    expect(find.textContaining('Five-layer quant validation required'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('VWAP Strategy').first,
      250,
      scrollable: strategyScroll,
    );
    expect(find.text('Candidate: WAIT • Approved decision: WAIT'), findsOneWidget);
    expect(find.textContaining('Underlying spot levels only—not option-premium prices'), findsWidgets);
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
