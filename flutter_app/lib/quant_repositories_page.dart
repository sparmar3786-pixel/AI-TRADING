import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// Curated research catalogue for the requested trading repositories.
/// Upstream code is not copied wholesale; this page links to source projects and
/// summarizes their research purpose. Each project must be reviewed/licensed
/// and adapted before code can safely be integrated into the APK.
class QuantRepositoriesPage extends StatelessWidget {
  const QuantRepositoriesPage({super.key});

  static const items = <(String, String, String, String)>[
    ('Awesome Systematic Trading', 'paperswithbacktest/awesome-systematic-trading', 'https://github.com/paperswithbacktest/awesome-systematic-trading', 'Systematic strategy research, backtesting concepts and related tools.'),
    ('Awesome Algorithmic Trading', 'joelowj/awesome-algorithmic-trading', 'https://github.com/joelowj/awesome-algorithmic-trading', 'Algorithmic-trading frameworks, libraries and learning references.'),
    ('Awesome Quant', 'wilsonfreitas/awesome-quant', 'https://github.com/wilsonfreitas/awesome-quant', 'Quantitative finance, pricing, analytics and research libraries.'),
    ('Awesome Deep Trading', 'cbailes/awesome-deep-trading', 'https://github.com/cbailes/awesome-deep-trading', 'Deep learning and machine-learning trading research references.'),
    ('Stock Market Dashboard', 'vikram-2101/Stock-Market-Dashboard', 'https://github.com/vikram-2101/Stock-Market-Dashboard', 'Dashboard and market-visualization reference.'),
    ('Stock Market Dashboard (DevMLAI01)', 'DevMLAI01/stock-market-dashboard', 'https://github.com/DevMLAI01/stock-market-dashboard', 'Stock dashboard / screener interface reference.'),
    ('Trade Engine', 'JasonTeixeira/trade-engine', 'https://github.com/JasonTeixeira/trade-engine', 'Trade-engine architecture reference; inspect broker and risk assumptions before adapting.'),
    ('AI Trading Signal Engine (FOREX)', 'keerthivasanrk/AI-Trading-Signal-Engine-FOREX-', 'https://github.com/keerthivasanrk/AI-Trading-Signal-Engine-FOREX-', 'Forex signal-engine reference; not automatically suitable for NSE instruments.'),
    ('Systematic Trading', 'karimcodes/systematic-trading', 'https://github.com/karimcodes/systematic-trading', 'Systematic strategy implementation and research reference.'),
    ('Backtest Kit', 'tripolskypetr/backtest-kit', 'https://github.com/tripolskypetr/backtest-kit', 'Backtesting toolkit reference; compare fill, costs and look-ahead handling.'),
  ];

  Future<void> _open(BuildContext context, String url) async {
    final uri = Uri.parse(url);
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open repository link. Please check your browser connection.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: [
      const Text('QUANT & TRADING REPOSITORIES', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 8),
      const Text('A single research library for all 10 repositories you listed. Tap any card to open its GitHub source. These are curated references, not claims that upstream code has been cloned or executed inside this APK.', style: TextStyle(color: Colors.white70)),
      const SizedBox(height: 10),
      Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
        Text('INTEGRATION POLICY', style: TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF12D6FF))),
        SizedBox(height: 6),
        Text('Before porting code: review each repository’s current licence, dependency stack, data-provider assumptions and tests. No broker keys or API secrets should be stored in the APK. Do not use a research link as a live signal without validation.'),
      ]))),
      const SizedBox(height: 8),
      for (final item in items)
        Card(
          child: ListTile(
            leading: const Icon(Icons.account_tree_outlined, color: Color(0xFF12D6FF), size: 28),
            title: Text(item.$1, style: const TextStyle(fontWeight: FontWeight.w800)),
            subtitle: Padding(padding: const EdgeInsets.only(top: 4), child: Text('${item.$2}\n${item.$4}')),
            isThreeLine: true,
            trailing: const Icon(Icons.open_in_new),
            onTap: () => _open(context, item.$3),
          ),
        ),
      const SizedBox(height: 8),
      const Text('BACKTESTING NOTE', style: TextStyle(fontWeight: FontWeight.w900)),
      const SizedBox(height: 4),
      const Text('The app’s historical backtest is implemented in Fresh-Apk backend at POST /v1/backtest/historical. If it returns HTTP 404, verify the deployed service’s /openapi.json and redeploy the backend from the same branch. A successful APK build alone does not deploy the Railway backend.', style: TextStyle(color: Colors.white70)),
    ],
  );
}
