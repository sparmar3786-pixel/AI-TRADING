import 'package:flutter/material.dart';
import 'api.dart';

class PerformancePage extends StatefulWidget {
  const PerformancePage({
    required this.backendUrl,
    required this.signalBackendUrl,
    super.key,
  });

  final String backendUrl;
  final String signalBackendUrl;

  @override
  State<PerformancePage> createState() => _PerformancePageState();
}

class _PerformancePageState extends State<PerformancePage> {
  Map<String, dynamic> _report = <String, dynamic>{};
  bool _loading = false;
  String? _error;

  Map<String, dynamic> _map(Object? value) =>
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await FreshApi(
        widget.backendUrl,
        null,
        widget.signalBackendUrl,
      ).getJson('/v1/paper/report', timeout: const Duration(seconds: 15));
      if (!mounted) return;
      setState(() => _report = response);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _count(Object? value) => value is num ? value.toInt().toString() : '—';

  String _rate(Object? value) {
    if (value is! num || !value.isFinite) return '—';
    return '${(value * 100).toStringAsFixed(1)}%';
  }

  String _number(Object? value, {String suffix = ''}) {
    if (value is! num || !value.isFinite) return '—';
    return '${value.toStringAsFixed(2)}$suffix';
  }

  String _rupees(Object? value) {
    if (value is! num || !value.isFinite) return 'Not recorded';
    final sign = value < 0 ? '-₹' : '₹';
    return '$sign${value.abs().toStringAsFixed(2)}';
  }

  Widget _metric(String label, String value) => Expanded(
        child: Container(
          margin: const EdgeInsets.only(right: 8, bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF101827),
            border: Border.all(color: const Color(0xFF263449)),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: const TextStyle(color: Colors.white60, fontSize: 11)),
              const SizedBox(height: 6),
              Text(value, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800)),
            ],
          ),
        ),
      );

  Widget _metricRow(List<Widget> children) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: children,
      );

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final metrics = _map(_report['metrics']);
    final byInstrument = _map(_report['by_instrument']);
    final accuracyStatus = (_report['accuracy_status'] ?? 'UNVERIFIED_NO_CLOSED_TRADES').toString();
    final hasClosedTrades = (_report['trade_count'] as num? ?? 0) > 0;

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(14),
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF101827),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFF263449)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Expanded(
                      child: Text('TRADE PERFORMANCE', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900, letterSpacing: 1)),
                    ),
                    IconButton(
                      tooltip: 'Refresh performance',
                      onPressed: _loading ? null : _load,
                      icon: _loading
                          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.refresh),
                    ),
                  ],
                ),
                const Text(
                  'Paper-trade outcomes only • no live order placement',
                  style: TextStyle(color: Colors.white60, fontSize: 12),
                ),
                const SizedBox(height: 12),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: hasClosedTrades ? const Color(0xFF123026) : const Color(0xFF352916),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    hasClosedTrades
                        ? 'RECORDED PAPER OUTCOMES • ${_count(_report['trade_count'])} closed trades'
                        : 'ACCURACY NOT VERIFIED • No closed trade outcomes recorded yet',
                    style: TextStyle(
                      color: hasClosedTrades ? Colors.greenAccent : Colors.orangeAccent,
                      fontWeight: FontWeight.w800,
                      fontSize: 12,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                _metricRow([
                  _metric('Win rate', _rate(metrics['win_rate'])),
                  _metric('Loss rate', _rate(metrics['loss_rate'])),
                ]),
                _metricRow([
                  _metric('Target hits', _count(metrics['target_hits'])),
                  _metric('Stop-loss hits', _count(metrics['stop_loss_hits'])),
                ]),
                _metricRow([
                  _metric('Net total (R)', _number(metrics['net_total_r'])),
                  _metric('Net P&L (₹)', _rupees(metrics['net_pnl_inr'])),
                ]),
                _metricRow([
                  _metric('Open trades', _count(metrics['open_trade_count'])),
                  _metric('Closed trades', _count(metrics['trade_count'])),
                ]),
                Text(
                  'P&L status: ${metrics['pnl_status'] ?? 'NOT_AVAILABLE_FOR_ALL_TRADES'} • Costs: ${metrics['total_costs_status'] ?? 'NOT_AVAILABLE_FOR_ALL_TRADES'}',
                  style: const TextStyle(color: Colors.white54, fontSize: 10),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          if (_error != null)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF351919),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.redAccent.withValues(alpha: 0.45)),
              ),
              child: Text('Performance report unavailable: $_error', style: const TextStyle(color: Colors.redAccent)),
            ),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFF101827),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFF263449)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('INSTRUMENT-WISE ACCURACY', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, letterSpacing: 0.7)),
                const SizedBox(height: 6),
                const Text(
                  'Only explicitly closed paper trades count. Target/SL totals come from the recorded exit reason; missing INR costs remain unreported rather than assumed zero.',
                  style: TextStyle(color: Colors.white60, fontSize: 11),
                ),
                const SizedBox(height: 12),
                if (byInstrument.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 18),
                    child: Center(child: Text('No instrument-wise results yet', style: TextStyle(color: Colors.white54))),
                  ),
                for (final entry in byInstrument.entries.toList()..sort((a, b) => a.key.compareTo(b.key)))
                  Container(
                    margin: const EdgeInsets.only(bottom: 10),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFF0A111D),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFF263449)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(child: Text(entry.key, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900))),
                            Text('${_count(_map(entry.value)['trade_count'])} trades', style: const TextStyle(color: Colors.white60, fontSize: 11)),
                          ],
                        ),
                        const SizedBox(height: 10),
                        _metricRow([
                          _metric('Win', _rate(_map(entry.value)['win_rate'])),
                          _metric('Loss', _rate(_map(entry.value)['loss_rate'])),
                        ]),
                        _metricRow([
                          _metric('Targets', _count(_map(entry.value)['target_hits'])),
                          _metric('Stop-loss', _count(_map(entry.value)['stop_loss_hits'])),
                        ]),
                        _metricRow([
                          _metric('Net R', _number(_map(entry.value)['net_total_r'])),
                          _metric('Net ₹ P&L', _rupees(_map(entry.value)['net_pnl_inr'])),
                        ]),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Important: this page measures recorded paper trades, not proven live-signal accuracy or realized broker P&L. Do not treat historical outcomes as a guarantee of future performance.',
            style: TextStyle(color: Colors.orangeAccent, fontSize: 11),
          ),
        ],
      ),
    );
  }
}
