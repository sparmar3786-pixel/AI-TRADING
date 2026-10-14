import 'dart:async';

import 'package:flutter/material.dart';
import 'api.dart';

/// Displays the backend's 15-minute Exa/Tavily news refresh and NVIDIA summary.
/// The page never makes up market prices or creates a trade signal.
class MarketIntelligencePage extends StatefulWidget {
  const MarketIntelligencePage({
    required this.backendUrl,
    required this.signalBackendUrl,
    super.key,
  });

  final String backendUrl;
  final String signalBackendUrl;

  @override
  State<MarketIntelligencePage> createState() => _MarketIntelligencePageState();
}

class _MarketIntelligencePageState extends State<MarketIntelligencePage> {
  Map<String, dynamic> _state = const <String, dynamic>{};
  String? _error;
  bool _loading = false;
  Timer? _pollTimer;

  FreshApi get _api => FreshApi(widget.backendUrl, null, widget.signalBackendUrl);

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(const Duration(minutes: 1), (_) => _load(silent: true));
  }

  @override
  void didUpdateWidget(covariant MarketIntelligencePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.backendUrl != widget.backendUrl ||
        oldWidget.signalBackendUrl != widget.signalBackendUrl) {
      _load();
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (_loading) return;
    _loading = true;
    if (!silent && mounted) setState(() => _error = null);
    try {
      final result = await _api.getJson(
        '/v1/market-intelligence',
        timeout: const Duration(seconds: 15),
      );
      if (!mounted) return;
      setState(() {
        _state = result;
        _error = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      _loading = false;
    }
  }

  Future<void> _refreshNow() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await _api.postJson(
        '/v1/market-intelligence/refresh',
        const <String, dynamic>{},
        timeout: const Duration(seconds: 15),
      );
      if (!mounted) return;
      setState(() => _state = result);
      await _load(silent: true);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _formatTime(dynamic raw) {
    if (raw == null || raw.toString().isEmpty) return 'Not available yet';
    final parsed = DateTime.tryParse(raw.toString())?.toLocal();
    if (parsed == null) return raw.toString();
    return '${parsed.day.toString().padLeft(2, '0')}-${parsed.month.toString().padLeft(2, '0')} ${parsed.hour.toString().padLeft(2, '0')}:${parsed.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final status = (_state['status'] ?? 'CONNECTING').toString();
    final summary = (_state['summary'] ?? '').toString();
    final articles = (_state['articles'] as List?) ?? const <dynamic>[];
    final checks = Map<String, dynamic>.from(
      _state['provider_checks'] as Map? ?? const <String, dynamic>{},
    );
    final indexNews = Map<String, dynamic>.from(
      _state['index_news'] as Map? ?? const <String, dynamic>{},
    );
    final isReady = status == 'READY' && summary.isNotEmpty;

    return RefreshIndicator(
      onRefresh: () => _load(),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(12),
        children: [
          const Text(
            'NVIDIA MARKET INTELLIGENCE',
            style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1),
          ),
          const SizedBox(height: 6),
          const Text(
            'Exa + Tavily headline evidence is refreshed by the backend every 15 minutes. '
            'NVIDIA summarizes the evidence; this page is research-only and never places orders.',
            style: TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(
                        isReady ? Icons.check_circle : Icons.info_outline,
                        color: isReady ? Colors.greenAccent : Colors.orangeAccent,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          status.replaceAll('_', ' '),
                          style: const TextStyle(fontWeight: FontWeight.w900),
                        ),
                      ),
                      IconButton(
                        tooltip: 'Refresh market intelligence now',
                        onPressed: _loading ? null : _refreshNow,
                        icon: const Icon(Icons.refresh),
                      ),
                    ],
                  ),
                  Text('Last updated: ${_formatTime(_state['updated_at'])}'),
                  Text('Next scheduled refresh: ${_formatTime(_state['next_refresh_at'])}'),
                  Text('AI summary provider: ${_state['summary_provider'] ?? 'Not confirmed'}'),
                  Text('Model: ${_state['summary_model'] ?? 'Not confirmed'}'),
                  if (_state['refreshing'] == true)
                    const Padding(
                      padding: EdgeInsets.only(top: 8),
                      child: LinearProgressIndicator(),
                    ),
                  if (_state['summary_error'] != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        'NVIDIA: ${_state['summary_error']}',
                        style: const TextStyle(color: Colors.orangeAccent),
                      ),
                    ),
                  if (_state['error'] != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        _state['error'].toString(),
                        style: const TextStyle(color: Colors.orangeAccent),
                      ),
                    ),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        'Connection error: $_error',
                        style: const TextStyle(color: Colors.redAccent),
                      ),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Text('NVIDIA MARKET BRIEF', style: TextStyle(fontWeight: FontWeight.w900)),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Text(
                summary.isNotEmpty
                    ? summary
                    : 'Waiting for the first Exa/Tavily refresh and NVIDIA inference. '
                        'If NVIDIA credentials or news-provider access fail, the status above will show it.',
                style: const TextStyle(height: 1.45),
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Text('NEWS PROVIDERS', style: TextStyle(fontWeight: FontWeight.w900)),
          for (final provider in const ['exa', 'tavily'])
            Builder(builder: (context) {
              final check = Map<String, dynamic>.from(
                checks[provider] as Map? ?? const <String, dynamic>{},
              );
              final ok = check['ok'] == true;
              return Card(
                child: ListTile(
                  leading: Icon(
                    ok ? Icons.check_circle : Icons.error_outline,
                    color: ok ? Colors.greenAccent : Colors.orangeAccent,
                  ),
                  title: Text(provider.toUpperCase()),
                  subtitle: Text(
                    'Status: ${check['last_error_status'] ?? (ok ? 'ok' : check['configured'] == true ? 'not verified' : 'not configured')}'
                    ' • Results: ${check['result_count'] ?? 0}'
                    ' • Indexes checked: ${check['indexes_checked'] ?? 0}',
                  ),
                ),
              );
            }),
          const SizedBox(height: 8),
          const Text('INDEX NEWS COVERAGE', style: TextStyle(fontWeight: FontWeight.w900)),
          for (final entry in indexNews.entries)
            Builder(builder: (context) {
              final row = Map<String, dynamic>.from(entry.value as Map? ?? const {});
              return Card(
                child: ListTile(
                  title: Text(entry.key),
                  subtitle: Text(
                    'News: ${row['article_count'] ?? 0} • Sentiment: ${row['label'] ?? 'UNKNOWN'}'
                    ' • Sources: ${(row['sources'] as List? ?? const []).join(', ')}',
                  ),
                ),
              );
            }),
          const SizedBox(height: 8),
          Text(
            'SOURCE-BACKED HEADLINES (${articles.length})',
            style: const TextStyle(fontWeight: FontWeight.w900),
          ),
          if (articles.isEmpty)
            const Card(
              child: ListTile(
                leading: Icon(Icons.newspaper),
                title: Text('No verified headlines available yet'),
                subtitle: Text('Check Exa/Tavily status and backend logs.'),
              ),
            ),
          for (final raw in articles)
            if (raw is Map)
              Card(
                child: ListTile(
                  leading: const Icon(Icons.article_outlined),
                  title: Text((raw['title'] ?? 'Untitled headline').toString()),
                  subtitle: Text(
                    '${raw['index'] ?? 'Market'} • ${raw['source'] ?? 'Unknown source'}'
                    ' • ${raw['published_at'] ?? 'Publish time unavailable'}',
                  ),
                  onTap: (raw['url'] is String && (raw['url'] as String).startsWith('https://'))
                      ? () => _openHeadline(raw['url'] as String)
                      : null,
                ),
              ),
          const SizedBox(height: 16),
          const Text(
            'Research only: headlines and AI summaries are not guaranteed to be complete or correct. '
            'Live quotes are included only when the backend marks them fresh; all trading decisions remain subject to deterministic validation and risk gates.',
            style: TextStyle(color: Colors.white60, fontSize: 12),
          ),
        ],
      ),
    );
  }

  Future<void> _openHeadline(String url) async {
    // Keep the news list safe and avoid adding a new navigation dependency.
    // The full URL remains visible/copyable in the evidence payload if no browser action is available.
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Source URL'),
        content: SelectableText(url),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        ],
      ),
    );
  }
}
