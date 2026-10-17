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
    expect(tabs, isNot(contains('API & Railway')));
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
    const sourceByLabel = <String, String>{
      'OI Price Action': 'Source: quant/oi_price_action_engine.py',
      'Hero Zero': 'Source: quant/hero_zero.py',
      'Failed-Move / PDH-PDL': 'Source: quant/failed_move_fade.py',
      'EMA Crossover': 'Source: quant/ema_quant_engine.py',
      'DAY-HL Liquidity Sweep': 'Source: quant/day_hl_liquidity.py',
      'Opening Range Breakout (ORB)': 'Source: quant/orb_engine.py',
      'VWAP Strategy': 'Source: quant/vwap_strategy.py',
    };
    for (final entry in sourceByLabel.entries) {
      expect(find.text(entry.value), findsOneWidget,
          reason: entry.key + ' inventory entry must be in the Strategies tab');
    }
    // Each strategy title must render exactly once; candidate data belongs in
    // the same card, not in a second parallel candidate list.
    for (final title in sourceByLabel.keys) {
      expect(find.text(title), findsOneWidget,
          reason: '$title must not be duplicated or overlap another card');
    }
    expect(find.byType(Card), findsNWidgets(8),
        reason: 'Seven strategy cards plus one safety card are expected.');
    expect(find.text('Expiry and fresh option quotes required; candidate is not actionable'), findsOneWidget);
  });

  testWidgets('Strategy Library renders all seven canonical backend candidates as WAIT-gated', (tester) async {
    tester.view.physicalSize = const Size(1200, 5000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final candidate = (String decision, String reason) => <String, dynamic>{
      'candidate_decision': decision,
      'decision': 'WAIT',
      'entry': 25000.0,
      'stop_loss': 24900.0,
      'target': 25200.0,
      'data_fresh': true,
      'reasons': <String>[reason],
      'guards': <String>['OPTION_CONTRACT_MAPPING_REQUIRED'],
      'live_validation': <String, dynamic>{
        'verdict': 'PENDING',
        'decision': 'WAIT',
        'blocks': <String>['Five-layer Quant and risk validation required'],
      },
    };

    await tester.pumpWidget(MaterialApp(
      home: StrategyLibraryPage(
        selectedIndex: 'NIFTY',
        signals: {
          'NIFTY': {
            'strategy_candidates': {
              'oi_price_action': candidate('PUT BUY', 'OI pressure candidate'),
              'hero_zero': candidate('CALL BUY', 'Expiry contract candidate'),
              'failed_move_pdh_pdl': candidate('PUT BUY', 'Failed move candidate'),
              'ema_crossover': candidate('CALL BUY', 'EMA cross candidate'),
              'day_hl_liquidity_sweep': {
                'decision': 'WAIT',
                'candidate_decision': null,
                'data_fresh': true,
                'entry': null,
                'stop_loss': null,
                'target': null,
                'reasons': <String>['Sweep detected; detector-only'],
                'guards': <String>['DETECTOR_ONLY'],
              },
              'orb': candidate('CALL BUY', 'ORB candidate'),
              'vwap': candidate('PUT BUY', 'VWAP candidate'),
            },
          },
        },
      ),
    ));
    await tester.pumpAndSettle();

    for (final key in <String>[
      'candidate-card-oi-price-action',
      'candidate-card-hero-zero',
      'candidate-card-failed-move-pdh-pdl',
      'candidate-card-ema-crossover',
      'candidate-card-day-hl-liquidity-sweep',
      'candidate-card-orb',
      'candidate-card-vwap',
    ]) {
      // The tall viewport renders all seven canonical cards; do not scroll to
      // obsolete duplicate candidate cards or depend on a fragile Scrollable finder.
      expect(find.byKey(ValueKey(key)), findsOneWidget,
          reason: '$key must render from canonical strategy_candidates');
    }
    expect(find.textContaining('Approved decision: WAIT'), findsWidgets);
    expect(find.textContaining('Underlying spot levels only—not option-premium prices'), findsWidgets);
    expect(find.textContaining('Sweep detected; detector-only'), findsOneWidget);
  });

  testWidgets('Strategy Library shows ORB/VWAP backend candidates but keeps them non-actionable', (tester) async {
    // Keep the complete canonical cards in the test viewport so assertions
    // verify rendered content, not a removed/duplicated legacy candidate card.
    tester.view.physicalSize = const Size(1200, 5000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

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
    final orbCard = find.byKey(const ValueKey('candidate-card-orb'));
    expect(orbCard, findsOneWidget);
    expect(
      find.descendant(of: orbCard, matching: find.textContaining('Candidate: CALL BUY')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: orbCard, matching: find.textContaining('Approved decision: WAIT')),
      findsOneWidget,
      reason: 'Candidate direction must never override the approved WAIT gate.',
    );

    final orbLevels = find.byKey(const ValueKey('candidate-levels-orb'));
    expect(orbLevels, findsOneWidget);
    final levelsText = tester.widget<Text>(orbLevels).data!;
    expect(levelsText, contains('Underlying entry: 25000.0'));
    expect(levelsText, contains('SL: 24900.0'));
    expect(levelsText, contains('Target: 25200.0'));
    expect(find.textContaining('Five-layer quant validation required'), findsOneWidget);

    final vwapCard = find.byKey(const ValueKey('candidate-card-vwap'));
    expect(vwapCard, findsOneWidget);
    expect(
      find.descendant(of: vwapCard, matching: find.textContaining('Candidate: WAIT')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('candidate-levels-vwap')), findsOneWidget);
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
    // Layer-level PASS labels may be present; the overall quant verdict must stay WAIT.
  });

  testWidgets('Quant Engine rejects conflicting top-level and nested stability states', (tester) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final timestamp = DateTime.now().toUtc().toIso8601String();
    final since = DateTime.now().toUtc().subtract(const Duration(seconds: 700)).toIso8601String();
    final layers = <String, dynamic>{
      'data_quality': {'name': 'Data freshness', 'status': 'PASS', 'detail': 'Fresh timestamp.'},
      'trend_sentiment': {'name': 'Trend & sentiment', 'status': 'PASS', 'detail': 'Trend aligned.'},
      'order_flow': {'name': 'Order-flow validation', 'status': 'PASS', 'detail': 'Depth valid.'},
      'option_selection': {'name': 'Option selection & liquidity', 'status': 'PASS', 'detail': 'Contract valid.'},
      'risk_levels': {'name': 'Risk & 10-minute stability', 'status': 'PASS', 'detail': 'Risk levels valid.'},
    };
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: QuantEnginePage(
          selectedIndex: 'NIFTY',
          signals: {
            'NIFTY': {
              'decision': 'CALL BUY',
              'signal_stability': {
                'state': 'BLOCKED', 'required_seconds': 600, 'since_utc': since,
              },
              'quant_engine': {
                'layers': layers, 'decision': 'CALL BUY', 'timestamp': timestamp,
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
    expect(find.textContaining('timer unverified'), findsNothing);
    expect(find.textContaining('Backend says CONFIRMED, but the 600-second timer evidence is missing'), findsOneWidget);
  });

}
