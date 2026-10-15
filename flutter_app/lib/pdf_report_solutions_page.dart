import 'package:flutter/material.dart';

/// In-app, page-by-page companion to Fresh_Algo_Signal_Screenshots_Error_Report.pdf.
/// Keeps the existing trading UI untouched and adds the report as a separate tab.
class PdfReportSolutionsPage extends StatelessWidget {
  const PdfReportSolutionsPage({super.key});

  static const pages = <(String, String, List<String>)>[
    ('PDF Page 1 • Summary, errors & meanings', 'What the screenshots show and what each status means', [
      'API OK: the Android app can reach the Railway backend. This alone does not prove Angel One is authenticated.',
      'Backtest HTTP 404: the app path may not match a deployed backend route; compare the app request with FastAPI /docs and deploy matching backend code.',
      'STALE_MARKET_DATA: report measured tick age about 28,244.83 seconds and 0/6 fresh indexes. Test during NSE hours (Monday–Friday, 9:15 AM–3:30 PM IST); if still stale, inspect Angel login and WebSocket reconnect logs.',
      'Angel One login CHECK / Authenticated session required: re-run SmartAPI login with the correct Client ID, PIN and TOTP; verify Railway variables and TOTP configuration without exposing secrets.',
      'AI_NOT_VALIDATED / AI_RESULT_STALE / AI_DIRECTION_MISMATCH / AI_CONFIDENCE_TOO_LOW / AI_STATUS_NOT_HEALTHY: first restore fresh market data, then verify the server-side OpenAI key, billing/quota and backend logs.',
      'OPTION_QUOTE_NOT_UNIQUE / STALE_OPTION_QUOTE / INVALID_BID_ASK / OPTION_SPREAD_TOO_WIDE / SIGNAL_OPTION_SIDE_MISMATCH: verify live quote freshness, unique contract mapping, bid/ask validity and spread checks.',
      'NO_QUALIFIED_STRATEGY_SIGNAL / STRATEGY_GUARDS_PRESENT / STRATEGY_CONFIDENCE_TOO_LOW / INVALID_ENTRY_SL_TARGET / REWARD_RISK_TOO_LOW / ENTRY_DIFFERS_FROM_LIVE_ASK: restore fresh candles and quotes; do not bypass strategy guards.',
      'Risk & Validation FAIL and final WAIT are fail-closed safety outcomes while checks are blocked, not a reason to force a trade.',
    ]),
    ('PDF Page 2 • Root-cause chain & fix order', 'Follow the sequence in the report; do not treat downstream blocks as separate fixes', [
      'Root-cause chain: Angel One session missing/expired → no fresh WebSocket ticks → stale index snapshots → no qualified strategy candidate → stale/invalid option quotes → entry/SL/target and reward/risk unavailable → AI result absent/stale → Layer 2 FAIL → final WAIT.',
      'Step 1: test during market hours; weekend/closed-market snapshots may naturally be stale.',
      'Step 2: authenticate Angel One SmartAPI on the backend; confirm credentials and TOTP variables in Railway without putting secrets in the APK or Git.',
      'Step 3: inspect Railway logs for login failures, WebSocket disconnects/reconnects and AI provider errors.',
      'Step 4: compare the app backtest request path against deployed FastAPI /docs; align route and client URL, then deploy the matching backend.',
      'Step 5: verify OpenAI key, billing/quota and logs after fresh market data is available.',
      'Step 6: validate in signal-only mode first. Live execution stays disabled until every gate passes and a human explicitly authorizes it.',
      'The PDF says exact causes still require Railway logs and /docs verification; this screen does not claim remote runtime checks were completed.',
    ]),
    ('PDF Page 3 • Screenshots 1–2', 'Indicators tab', [
      'Screenshot 1: Indicators tab — indicator and strategy status.'
      'Screenshot 2: Indicators tab — additional indicator status.'
      'This report focuses on in-app trading workflows and validation status.'
    ]),
    ('PDF Page 4 • Screenshots 3–4', 'Signals validation and Backtesting 404', [
      'Screenshot 3: Signals tab — validation blocks and Angel One Live Execution shown DISABLED.',
      'Screenshot 4: Backtesting tab — Backtest failed: HTTP 404: Not Found.',
      'Fix the backtest route by comparing the deployed API route and app URL; keep live execution disabled while validation is blocked.',
    ]),
    ('PDF Page 5 • Screenshots 5–6', 'Removed reference pages', [
      'The app should show only trading workflows, live status and validation results on this page.'
    ]),
    ('PDF Page 6 • Screenshots 7–8', 'Trading Setup checklist and system flow', [
      'Screenshot 7: Live Setup Checklist — Angel login, live data and AI show CHECK.',
      'Screenshot 8: Trading Setup — system flow and module list.',
      'Use the checklist to verify broker authentication, fresh ticks and AI response in that order.',
    ]),
    ('PDF Page 7 • Screenshots 9–10', 'Trading Setup modules', [
      'Screenshot 9: Trading Setup — modules 2 to 8.',
      'Screenshot 10: Trading Setup — modules 5 to 9 and disclaimer.',
      'Treat module status as evidence from the app/backend; do not mark a module healthy just because its screen exists.',
    ]),
    ('PDF Page 8 • Screenshots 11–12', 'Research Engines and validation output', [
      'Research Engines shows live backend indicator, OI, confluence and validation outputs.',
      'Research Engines shows only live backend indicator, OI, confluence and validation outputs.'
    ]),
    ('PDF Page 9 • Screenshots 13–14', '3-Layer engine blocks and disabled monitor', [
      'Screenshot 13: Blocking reasons and Trade Monitor DISABLED.',
      'Screenshot 14: Layer checks show BLOCK / PASS; stale data and other guards explain the blocks.',
      'Do not enable the Trade Monitor or live order path to hide validation failures.',
    ]),
    ('PDF Page 10 • Screenshot 15', 'Final Risk & Validation FAIL / WAIT', [
      'Screenshot 15: Layer 2 RISK & VALIDATION = FAIL; final action WAIT.',
      'Expected safe behavior while upstream checks fail. Re-test only after the session, data freshness, quote quality, strategy, AI and risk checks are genuinely passing.',
    ]),
  ];

  static const screenshotCaptions = <String>[
    '1. Indicators — live indicator snapshot',
    '2. Indicators — advanced indicator snapshot',
    '3. Signals — validation blocks and Live Execution DISABLED',
    '4. Backtesting — HTTP 404',
    '5. Trading workflow page',
    '6. Trading workflow page',
    '7. Trading Setup — live setup checklist',
    '8. Trading Setup — system flow and modules',
    '9. Trading Setup — modules 2 to 8',
    '10. Trading Setup — modules 5 to 9 and disclaimer',
    '11. Research Engines — live validation output',
    '12. 3-Layer Trade Engine — deterministic checks',
    '13. 3-Layer Trade Engine — blocking reasons and disabled monitor',
    '14. 3-Layer Trade Engine — all checks',
    '15. 3-Layer Trade Engine — Risk & Validation FAIL / WAIT',
  ];

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('PDF REPORT • ALL 10 PAGES & FIX CHECKLIST',
          style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 6),
      const Text(
        'In-app transcription and structured guide based on the uploaded 10-page screenshot report. All 15 screenshot captions are indexed below. This is report content in a new tab, not an embedded pixel-for-pixel PDF viewer.',
        style: TextStyle(color: Colors.white70, fontSize: 12)),
      const SizedBox(height: 12),
      Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          Text('PRIORITY ROOT CAUSE', style: TextStyle(fontWeight: FontWeight.w900, color: Colors.orangeAccent)),
          SizedBox(height: 8),
          Text('Angel One session → fresh WebSocket ticks → valid option quotes → strategy candidate → AI validation → deterministic risk gate.'),
          SizedBox(height: 8),
          Text('Do not bypass fail-closed safety checks or enable live orders to hide an error.',
              style: TextStyle(color: Colors.orangeAccent, fontWeight: FontWeight.w700)),
        ],
      ))),
      const Text('PAGE-BY-PAGE REPORT', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 6),
      for (final page in pages)
        Card(child: ExpansionTile(
          key: PageStorageKey<String>(page.$1),
          leading: const Icon(Icons.picture_as_pdf_outlined, color: Color(0xFF12D6FF)),
          title: Text(page.$1, style: const TextStyle(fontWeight: FontWeight.w800)),
          subtitle: Text(page.$2),
          children: [
            for (final paragraph in page.$3)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('•  ', style: TextStyle(color: Color(0xFF12D6FF))),
                  Expanded(child: Text(paragraph)),
                ]),
              ),
            const SizedBox(height: 8),
          ],
        )),
      const SizedBox(height: 8),
      const Text('ALL 15 SCREENSHOT INDEX', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 6),
      Card(child: Column(children: [
        for (var i = 0; i < screenshotCaptions.length; i++)
          ListTile(
            dense: true,
            leading: CircleAvatar(radius: 14, child: Text('${i + 1}', style: const TextStyle(fontSize: 11))),
            title: Text(screenshotCaptions[i], style: const TextStyle(fontSize: 12)),
          ),
      ])),
      const SizedBox(height: 8),
      const Text('SAFETY STATUS FROM THE PDF', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const Card(child: Column(children: [
        ListTile(leading: Icon(Icons.check_circle_outline, color: Colors.greenAccent), title: Text('API OK / Railway reachable'), subtitle: Text('The report says the backend responded; this does not guarantee Angel One is logged in.')),
        ListTile(leading: Icon(Icons.warning_amber_rounded, color: Colors.orangeAccent), title: Text('Angel One / market freshness / AI need verification'), subtitle: Text('Check actual login, WebSocket freshness and provider logs.')),
        ListTile(leading: Icon(Icons.shield_outlined, color: Colors.cyanAccent), title: Text('Live execution remains disabled'), subtitle: Text('Keep execution off while any required validation is blocked.')),
      ])),
    ],
  );
}
