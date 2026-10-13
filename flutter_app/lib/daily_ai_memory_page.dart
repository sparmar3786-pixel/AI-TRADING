import 'package:flutter/material.dart';
import 'daily_ai_memory.dart';

class DailyAiMemoryPage extends StatefulWidget {
  const DailyAiMemoryPage({super.key});

  @override
  State<DailyAiMemoryPage> createState() => _DailyAiMemoryPageState();
}

class _DailyAiMemoryPageState extends State<DailyAiMemoryPage> {
  Map<String, dynamic> _document = const {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final data = await DailyAiMemory.readDay(DateTime.now());
    if (!mounted) return;
    setState(() {
      _document = data;
      _loading = false;
    });
  }

  Map<String, dynamic> _map(dynamic value) =>
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

  @override
  Widget build(BuildContext context) {
    final snapshots = List<dynamic>.from(_document['snapshots'] as List? ?? const []);
    final latest = snapshots.isEmpty ? <String, dynamic>{} : _map(snapshots.last);
    final market = _map(latest['market_analysis']);
    final oi = _map(latest['oi_analysis']);
    final footprint = _map(latest['footprint_analysis']);
    return Scaffold(
      backgroundColor: const Color(0xFF070B12),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(children: [
              const Expanded(child: Text('DAILY AI MEMORY', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900))),
              IconButton(onPressed: _load, icon: const Icon(Icons.refresh), tooltip: 'Read today’s saved analysis'),
            ]),
            const Text('Observed market snapshots are saved on this phone once per minute. Stale or missing data is labelled, never filled with demo values.'),
            const SizedBox(height: 12),
            Card(child: ListTile(
              leading: const Icon(Icons.folder_open, color: Color(0xFF12D6FF)),
              title: const Text('Phone storage folder'),
              subtitle: Text(DailyAiMemory.lastWritePath ?? 'App-specific storage: Android/data/<app-id>/files/AI-TRADING/AI-Memory'),
              isThreeLine: true,
            )),
            Card(child: ListTile(
              leading: const Icon(Icons.calendar_month),
              title: Text(_document['date']?.toString() ?? 'Today'),
              subtitle: Text('${snapshots.length} saved snapshot(s) • one daily JSON file'),
              trailing: _loading ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.check_circle_outline),
            )),
            if (DailyAiMemory.lastWriteError != null)
              Card(child: ListTile(
                leading: const Icon(Icons.error_outline, color: Colors.orangeAccent),
                title: const Text('Memory write warning'),
                subtitle: Text(DailyAiMemory.lastWriteError!),
              )),
            const SizedBox(height: 8),
            const Text('LATEST OBSERVED MARKET ANALYSIS', style: TextStyle(fontWeight: FontWeight.w800)),
            if (market.isEmpty)
              const Card(child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('No saved snapshot for today yet. Keep the app open while the backend refreshes.'),
              )),
            for (final entry in market.entries)
              Card(child: ExpansionTile(
                title: Text(entry.key, style: const TextStyle(fontWeight: FontWeight.w800)),
                subtitle: Text('LTP ${_map(entry.value)['ltp'] ?? '—'} • ${_map(entry.value)['decision'] ?? 'WAIT'} • live=${_map(entry.value)['live'] == true}'),
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    child: SelectableText(_map(entry.value).toString()),
                  ),
                ],
              )),
            const SizedBox(height: 8),
            const Text('ORDER FLOW / SUPPORT / RESISTANCE', style: TextStyle(fontWeight: FontWeight.w800)),
            Card(child: ListTile(
              title: Text('Symbol: ${footprint['symbol'] ?? 'No footprint snapshot yet'}'),
              subtitle: Text('Support: ${footprint['support_from_observed_candle_lows'] ?? '—'} • Resistance: ${footprint['resistance_from_observed_candle_highs'] ?? '—'}\nWindow: ${footprint['window'] ?? 'Awaiting observed candles'}'),
              isThreeLine: true,
            )),
            const SizedBox(height: 8),
            const Text('OPEN-INTEREST BUILDUP / UNWINDING', style: TextStyle(fontWeight: FontWeight.w800)),
            if (oi.isEmpty)
              const Card(child: ListTile(title: Text('OI history is collecting'), subtitle: Text('OI classification needs two timestamped snapshots for the same contract.'))),
            for (final entry in oi.entries)
              Card(child: ExpansionTile(
                title: Text(entry.key),
                subtitle: Text('${(entry.value is Map ? (_map(entry.value)['events'] as List? ?? const []).length : 0)} contract observations'),
                children: [
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: SelectableText((_map(entry.value)['events'] ?? const []).toString()),
                  ),
                ],
              )),
            const SizedBox(height: 12),
            const Text('Historical coverage depends on broker/vendor retention. Angel One documents per-request caps (daily candles up to 2,000 days; intraday intervals have shorter windows). This journal records new observations and does not pretend to contain five years of history until that history is actually retrieved and verified.'),
          ],
        ),
      ),
    );
  }
}
