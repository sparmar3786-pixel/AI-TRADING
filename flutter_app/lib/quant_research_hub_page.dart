import 'package:flutter/material.dart';

/// Quant research status hub. No external repository links are rendered.
class QuantResearchHubPage extends StatelessWidget {
  const QuantResearchHubPage({super.key});

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: const [
      Text('QUANT RESEARCH HUB', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      SizedBox(height: 8),
      Text('Repository cards and outbound source links have been removed. Use the live backend outputs below to inspect what the app is actually calculating.', style: TextStyle(color: Colors.white70)),
      SizedBox(height: 12),
      Card(child: Column(children: [
        ListTile(leading: Icon(Icons.track_changes), title: Text('Strategy validation'), subtitle: Text('Deterministic strategies must pass freshness, conflict and risk checks')),
        Divider(height: 1),
        ListTile(leading: Icon(Icons.query_stats), title: Text('Backtesting and costs'), subtitle: Text('Use out-of-sample results and include brokerage, slippage and taxes')),
        Divider(height: 1),
        ListTile(leading: Icon(Icons.data_usage), title: Text('Market data quality'), subtitle: Text('Reject stale or incomplete quotes and show the latest verified timestamp')),
        Divider(height: 1),
        ListTile(leading: Icon(Icons.shield_outlined), title: Text('Risk gates'), subtitle: Text('Blocked validation returns WAIT / NO TRADE; it must not force an order')),
      ])),
    ],
  );
}
