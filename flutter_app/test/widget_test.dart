import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/main.dart';
import 'package:ai_trading_signal/strategy_library_page.dart';
import 'package:ai_trading_signal/quant_engine_page.dart';

void main() {
  testWidgets('Quant Engine shows layer blockers and never calls a closed-market snapshot LIVE', (tester) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final timestamp = DateTime.now().toUtc().toIso8601String();
    final layers = <String, dynamic>{
      'data_quality': {'name': 'Data freshness', 'status': 'FAIL', 'detail': 'Exchange timestamp is stale.'},
      'trend_sentiment': {'name': 'Trend & sentiment', 'status': 'FAIL', 'detail': 'Trend evidence unavailable.'},
      'order_flow': {'name': 'Order-flow validation', 'status': 'UNAVAILABLE', 'detail': 'Depth not returned.'},
      'option_selection': {'name': 'Option selection & liquidity', 'status': 'FAIL', 'detail': 'No fresh option quote.'},
      'risk_levels': {'name': 'Risk & 10-minute stability', 'status': 'FAIL', 'detail': 'Option ATR missing.'},
    };
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: QuantEnginePage(
          selectedIndex: 'NIFTY',
          signals: {
            'NIFTY': {
              'decision': 'WAIT',
              'reasons': ['Insufficient completed 5-minute candles'],
              'quant_engine': {
                'layers': layers,
                'decision': 'WAIT',
                'timestamp': timestamp,
                'data_fresh': false,
                'confirmation': {'state': 'BLOCKED', 'required_seconds': 600},
              },
            },
          },
          market: {'NIFTY': {'live': true, 'age_seconds': 9.2}},
          marketOpen: false,
          onIndexChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('BLOCK'), findsOneWidget);
    expect(find.textContaining('MARKET CLOSED'), findsOneWidget);
    expect(find.textContaining('Exchange timestamp is stale.'), findsOneWidget);
    expect(find.textContaining('Depth not returned.'), findsOneWidget);
    expect(find.text('Backend layer evidence not supplied.'), findsNothing);
  });

  testWidgets('Quant Engine falls back to canonical raw five-layer evidence', (tester) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final timestamp = DateTime.now().toUtc().toIso8601String();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: QuantEnginePage(
          selectedIndex: 'NIFTY',
          signals: {
            'NIFTY': {
              'decision': 'WAIT',
              'reasons': ['Market evidence is not fresh'],
              'quant_engine': {
                'layers': <String, dynamic>{},
                'timestamp': timestamp,
                'data_fresh': false,
                'confirmation': {'state': 'BLOCKED', 'required_seconds': 600},
              },
              'layers': {
                'data_quality': {'pass': false, 'reason': 'Exchange timestamp is stale.'},
                'trend_sentiment': {'pass': false, 'reason': 'Insufficient completed candles.'},
                'order_flow': {'pass': false, 'reason': 'Bid/ask depth unavailable.'},
                'option_selection': {'pass': false, 'reason': 'Fresh option quote missing.'},
                'risk_levels': {'pass': false, 'reason': 'Option ATR unavailable.'},
              },
            },
          },
          market: {'NIFTY': {'live': false, 'age_seconds': 30}},
          marketOpen: true,
          onIndexChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.textContaining('Exchange timestamp is stale.'), findsOneWidget);
    expect(find.textContaining('Bid/ask depth unavailable.'), findsOneWidget);
    expect(find.textContaining('Backend did not supply exactly five complete layer results'), findsNothing);
    expect(find.text('BLOCK'), findsOneWidget);
    expect(find.text('CALL BUY'), findsNothing);
    expect(find.text('PUT BUY'), findsNothing);
  });

  testWidgets('Quant Engine exposes missing backend reason while remaining DATA REQUIRED', (tester) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: QuantEnginePage(
          selectedIndex: 'NIFTY',
          signals: {
            'NIFTY': {
              'decision': 'WAIT',
              'reasons': ['Insufficient completed 5-minute candles'],
              'quant_engine': {
                'layers': {
                  'data_quality': {'name': 'Data freshness', 'status': 'UNAVAILABLE', 'detail': 'Insufficient completed 5-minute candles'},
                  'trend_sentiment': {'name': 'Trend & sentiment', 'status': 'UNAVAILABLE', 'detail': 'Insufficient completed 5-minute candles'},
                  'order_flow': {'name': 'Order-flow validation', 'status': 'UNAVAILABLE', 'detail': 'Insufficient completed 5-minute candles'},
                  'option_selection': {'name': 'Option selection & liquidity', 'status': 'UNAVAILABLE', 'detail': 'Insufficient completed 5-minute candles'},
                  'risk_levels': {'name': 'Risk & 10-minute stability', 'status': 'UNAVAILABLE', 'detail': 'Insufficient completed 5-minute candles'},
                },
                'decision': 'WAIT',
                'timestamp': null,
                'data_fresh': false,
                'confirmation': {'state': 'BLOCKED', 'required_seconds': 600},
              },
            },
          },
          market: {'NIFTY': {'live': false, 'age_seconds': null}},
          marketOpen: true,
          onIndexChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('DATA REQUIRED'), findsOneWidget);
    expect(find.textContaining('Insufficient completed 5-minute candles'), findsWidgets);
    expect(find.text('Backend layer evidence not supplied.'), findsNothing);
  });

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
    // Render the page directly at a tall test viewport. This verifies every
    // inventory card without relying on app-shell navigation or a fragile
    // scrollable finder that may not exist in the widget tree.
    tester.view.physicalSize = const Size(1200, 5000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const MaterialApp(
      home: StrategyLibraryPage(),
    ));
    await tester.pumpAndSettle();

    expect(find.text('STRATEGY LIBRARY'), findsOneWidget);
    for (final label in <String>[
      'OI Price Action',
      'Hero Zero',
      'Failed-Move / PDH-PDL',
      'EMA Crossover',
      'DAY-HL Liquidity Sweep',
      'Opening Range Breakout (ORB)',
      'VWAP Strategy',
    ]) {
      final labelFinder = label == 'Opening Range Breakout (ORB)'
          ? find.text('Source: quant/orb_engine.py')
          : (label == 'VWAP Strategy'
              ? find.text('Source: quant/vwap_strategy.py')
              : find.text(label));
      expect(labelFinder, findsOneWidget, reason: '$label must be in the Strategies tab');
    }
    expect(find.text('Expiry-only candidate; live API wiring not verified'), findsOneWidget);
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
      find.text('Candidate: CALL BUY • Approved decision: WAIT'),
      250,
      scrollable: strategyScroll,
    );
    expect(find.text('Candidate: CALL BUY • Approved decision: WAIT'), findsOneWidget);
    expect(find.textContaining('Underlying entry: 25000.0 • SL: 24900.0 • Target: 25200.0'), findsOneWidget);
    expect(find.textContaining('Five-layer quant validation required'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Candidate: WAIT • Approved decision: WAIT'),
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
  testWidgets('Quant Engine refuses CONFIRMED when 600-second timer evidence is absent', (tester) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final timestamp = DateTime.now().toUtc().toIso8601String();
    final layers = <String, dynamic>{
      'data_quality': {'name': 'Data freshness', 'status': 'PASS', 'detail': 'Fresh exchange timestamp and positive LTP.'},
      'trend_sentiment': {'name': 'Trend & sentiment', 'status': 'PASS', 'detail': 'Timeframes and sentiment align.'},
      'order_flow': {'name': 'Order-flow validation', 'status': 'PASS', 'detail': 'Fresh two-sided depth.'},
      'option_selection': {'name': 'Option selection & liquidity', 'status': 'PASS', 'detail': 'Fresh liquid option selected.'},
      'risk_levels': {'name': 'Risk & 10-minute stability', 'status': 'PASS', 'detail': 'Positive stop and target.'},
    };
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: QuantEnginePage(
          selectedIndex: 'NIFTY',
          signals: {
            'NIFTY': {
              'decision': 'CALL BUY',
              'signal_stability': {'state': 'CONFIRMED', 'required_seconds': 600},
              'quant_engine': {
                'layers': layers,
                'decision': 'CALL BUY',
                'timestamp': timestamp,
                'data_fresh': true,
                'confirmation': {'state': 'CONFIRMED', 'required_seconds': 600},
              },
            },
          },
          market: {'NIFTY': {'live': true, 'age_seconds': 1}},
          marketOpen: true,
          onIndexChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('WAIT'), findsOneWidget);
    expect(find.textContaining('timer unverified'), findsOneWidget);
    expect(find.textContaining('Backend says CONFIRMED, but the 600-second timer evidence is missing'), findsOneWidget);
    expect(find.text('PASS'), findsNothing);
  });

}
