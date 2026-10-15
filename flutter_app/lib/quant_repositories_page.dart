import 'package:flutter/material.dart';

/// Research status page without external repository links.
class QuantRepositoriesPage extends StatelessWidget {
  const QuantRepositoriesPage({super.key});

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(12),
    children: const [
      Text('QUANT & TRADING ENGINE STATUS', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      SizedBox(height: 8),
      Text('This page now shows the integrated trading workflow only. External repository cards and outbound source links have been removed.', style: TextStyle(color: Colors.white70)),
      SizedBox(height: 12),
      Card(child: Column(children: [
        ListTile(leading: Icon(Icons.show_chart), title: Text('Technical indicators'), subtitle: Text('EMA, SMA, RSI, MACD, ATR and volatility metrics')),
        Divider(height: 1),
        ListTile(leading: Icon(Icons.stacked_line_chart), title: Text('Options and open interest'), subtitle: Text('Option-chain snapshots, OI classification and PCR when backend data is available')),
        Divider(height: 1),
        ListTile(leading: Icon(Icons.verified_user_outlined), title: Text('Signal validation'), subtitle: Text('Freshness, strategy, AI evidence and deterministic risk gates')),
        Divider(height: 1),
        ListTile(leading: Icon(Icons.query_stats), title: Text('Backtesting'), subtitle: Text('Historical validation with realistic costs and out-of-sample checks')),
      ])),
    ],
  );
}
