import 'package:flutter/material.dart';
import 'api.dart';

const _prototypeIndexes = <String>[
  'NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX',
];

/// A separate broker-home prototype inspired by common Indian investing apps.
/// All market quotes come from Fresh's existing Angel One-backed market snapshot.
/// This screen deliberately contains no Groww API, SDK, endpoint, or credentials.
class BrokerHomePrototypePage extends StatefulWidget {
  const BrokerHomePrototypePage({
    required this.backendUrl,
    required this.market,
    required this.signals,
    required this.angelOnline,
    required this.status,
    required this.onIndexSelected,
    super.key,
  });

  final String backendUrl;
  final Map<String, dynamic> market;
  final Map<String, dynamic> signals;
  final bool angelOnline;
  final String status;
  final ValueChanged<String> onIndexSelected;

  @override
  State<BrokerHomePrototypePage> createState() => _BrokerHomePrototypePageState();
}

class _BrokerHomePrototypePageState extends State<BrokerHomePrototypePage> {
  String _section = 'Watchlist';
  String _query = '';
  bool _portfolioLoading = false;
  Map<String, dynamic>? _portfolio;
  String? _portfolioError;

  Future<void> _loadPortfolio() async {
    setState(() {
      _portfolioLoading = true;
      _portfolioError = null;
    });
    try {
      final result = await FreshApi(widget.backendUrl).portfolio();
      if (!mounted) return;
      setState(() => _portfolio = result);
    } catch (error) {
      if (!mounted) return;
      setState(() => _portfolioError = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _portfolioLoading = false);
    }
  }

  Widget _portfolioRows(String title, dynamic raw) {
    final rows = raw is List ? raw : const <dynamic>[];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w900)),
            const SizedBox(height: 6),
            if (rows.isEmpty)
              const Text('No rows returned by Angel One.', style: TextStyle(color: Colors.white70))
            else
              for (final row in rows)
                if (row is Map)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text((row['tradingsymbol'] ?? row['symbol'] ?? row['instrument'] ?? 'Instrument').toString()),
                    subtitle: Text(row.entries
                        .where((entry) => !['tradingsymbol', 'symbol', 'instrument'].contains(entry.key))
                        .take(4)
                        .map((entry) => '${entry.key}: ${entry.value}')
                        .join(' • ')),
                  )
                else
                  Text(row.toString()),
          ],
        ),
      ),
    );
  }

  Map<String, dynamic> _row(String index) =>
      Map<String, dynamic>.from(widget.market[index] as Map? ?? const {});

  String _price(dynamic value) {
    if (value is num && value > 0) return value.toStringAsFixed(2);
    return '—';
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _prototypeIndexes
        .where((name) => name.toLowerCase().contains(_query.trim().toLowerCase()))
        .toList();
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
      children: [
        Row(
          children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Invest', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
                const SizedBox(height: 3),
                Text('Markets, watchlist & account overview',
                    style: TextStyle(color: Colors.white.withOpacity(.65), fontSize: 12)),
              ]),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: widget.angelOnline ? const Color(0xFF12382F) : const Color(0xFF392B17),
                borderRadius: BorderRadius.circular(24),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.circle, size: 8,
                    color: widget.angelOnline ? Colors.greenAccent : Colors.orangeAccent),
                const SizedBox(width: 6),
                Text(widget.angelOnline ? 'ANGEL ONE' : 'CONNECT BROKER',
                    style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800)),
              ]),
            ),
          ],
        ),
        const SizedBox(height: 14),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('INDIAN MARKET WATCH', style: TextStyle(fontSize: 11, letterSpacing: 1, fontWeight: FontWeight.w800)),
              const SizedBox(height: 10),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final name in const ['NIFTY', 'BANKNIFTY', 'SENSEX'])
                  _marketChip(name, _row(name)),
              ]),
              const SizedBox(height: 10),
              Text(widget.status,
                  style: TextStyle(fontSize: 11, color: Colors.white.withOpacity(.65))),
            ]),
          ),
        ),
        const SizedBox(height: 12),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'Watchlist', label: Text('Watchlist'), icon: Icon(Icons.star_outline)),
            ButtonSegment(value: 'Portfolio', label: Text('Portfolio'), icon: Icon(Icons.pie_chart_outline)),
            ButtonSegment(value: 'Explore', label: Text('Explore'), icon: Icon(Icons.explore_outlined)),
          ],
          selected: {_section},
          onSelectionChanged: (values) => setState(() => _section = values.first),
        ),
        const SizedBox(height: 12),
        if (_section == 'Portfolio') ...[
          Card(child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Angel One portfolio', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              const Text('Live holdings and positions are requested from the connected backend; no sample balance or P&L is fabricated.',
                  style: TextStyle(fontSize: 12, color: Colors.white70)),
              const SizedBox(height: 10),
              FilledButton.icon(
                onPressed: _portfolioLoading ? null : _loadPortfolio,
                icon: _portfolioLoading
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.refresh),
                label: Text(_portfolioLoading ? 'Loading portfolio…' : 'Load live portfolio'),
              ),
              if (_portfolioError != null) ...[
                const SizedBox(height: 8),
                Text('Portfolio unavailable: $_portfolioError', style: const TextStyle(color: Colors.orangeAccent)),
              ],
            ]),
          )),
          if (_portfolio != null) ...[
            _portfolioRows('HOLDINGS', _portfolio!['holdings']),
            _portfolioRows('POSITIONS', _portfolio!['positions']),
          ],
          const SizedBox(height: 4),
          const Text('No Groww API or Groww account connection is used.',
              style: TextStyle(fontSize: 11, color: Colors.cyanAccent)),
        ] else ...[
          TextField(
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Search index watchlist',
              border: OutlineInputBorder(),
            ),
            onChanged: (value) => setState(() => _query = value),
          ),
          const SizedBox(height: 8),
          if (_section == 'Explore')
            const Card(child: ListTile(
              leading: Icon(Icons.auto_graph, color: Color(0xFF12D6FF)),
              title: Text('Market instruments'),
              subtitle: Text('Indian index watchlist sourced through the existing Angel One market feed.'),
            )),
          for (final name in filtered) _instrumentCard(name),
        ],
        const SizedBox(height: 10),
        const Text(
          'Prototype note: this is an additional screen. Existing Fresh Algo Signal pages and navigation are retained. Quotes appear only when the Angel One-backed backend supplies them; missing prices remain “—”.',
          style: TextStyle(fontSize: 11, color: Colors.white54),
        ),
      ],
    );
  }

  Widget _marketChip(String name, Map<String, dynamic> row) => Container(
    constraints: const BoxConstraints(minWidth: 100),
    padding: const EdgeInsets.all(10),
    decoration: BoxDecoration(
      color: const Color(0xFF172330),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(name, style: const TextStyle(fontSize: 10, color: Colors.white70)),
      const SizedBox(height: 4),
      Text(_price(row['ltp']), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w900)),
      Text(row['live'] == true ? 'LIVE FEED' : 'WAITING FOR DATA',
          style: TextStyle(fontSize: 8, color: row['live'] == true ? Colors.greenAccent : Colors.orangeAccent)),
    ]),
  );

  Widget _instrumentCard(String name) {
    final row = _row(name);
    final signal = Map<String, dynamic>.from(widget.signals[name] as Map? ?? const {});
    final live = row['live'] == true;
    final decision = (signal['decision'] ?? signal['signal'] ?? '—').toString();
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => widget.onIndexSelected(name),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 13),
          child: Row(children: [
            CircleAvatar(
              backgroundColor: const Color(0xFF17303D),
              child: Text(name.startsWith('BANK') ? 'B' : name.substring(0, 1),
                  style: const TextStyle(fontWeight: FontWeight.w900, color: Colors.cyanAccent)),
            ),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(name, style: const TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 3),
              Text(live ? 'Angel One • live tick' : 'Angel One • data unavailable',
                  style: const TextStyle(fontSize: 10, color: Colors.white60)),
            ])),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text(_price(row['ltp']), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w900)),
              const SizedBox(height: 3),
              Text('Signal: $decision', style: const TextStyle(fontSize: 10, color: Colors.cyanAccent)),
            ]),
          ]),
        ),
      ),
    );
  }
}
