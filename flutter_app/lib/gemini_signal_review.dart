import 'package:flutter/material.dart';
import 'api.dart';

/// On-demand Gemini review. Its prose is advisory and never changes the
/// deterministic signal or promotes a WAIT to PASS.
class GeminiSignalReview extends StatefulWidget {
  const GeminiSignalReview({
    required this.backendUrl,
    required this.selectedIndex,
    super.key,
  });

  final String backendUrl;
  final String selectedIndex;

  @override
  State<GeminiSignalReview> createState() => _GeminiSignalReviewState();
}

class _GeminiSignalReviewState extends State<GeminiSignalReview> {
  bool _busy = false;
  bool _connected = false;
  String? _answer;
  String? _error;
  String _model = 'Gemini not tested';

  @override
  void didUpdateWidget(covariant GeminiSignalReview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selectedIndex != widget.selectedIndex) {
      _answer = null;
      _error = null;
      _connected = false;
      _model = 'Gemini not tested';
    }
  }

  Future<void> _review() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final response = await FreshApi(widget.backendUrl).reviewSignalWithGemini(index: widget.selectedIndex);
      final provider = (response['provider'] ?? 'unknown').toString().toLowerCase();
      final used = response['ok'] == true && provider == 'gemini';
      final verdict = (response['verdict'] ?? 'WAIT').toString().toUpperCase();
      final decision = (response['decision'] ?? 'WAIT').toString().toUpperCase();
      final reason = (response['reason'] ?? 'No review reason returned.').toString();
      final blocks = (response['blocks'] as List? ?? const []).map((item) => item.toString()).join(', ');
      final answer = 'Gemini verdict: $verdict • Decision: $decision\n$reason'
          '${blocks.isEmpty ? '' : '\nBlocking checks: $blocks'}';
      if (!mounted) return;
      setState(() {
        _connected = used;
        _model = used
            ? 'CONNECTED • ${response['model'] ?? 'Gemini'} • ${response['latency_ms'] ?? '—'} ms'
            : 'NOT VERIFIED • ${response['status'] ?? provider}';
        _answer = answer;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _connected = false;
        _error = error.toString().replaceFirst('Exception: ', '');
        _model = 'NOT CONNECTED';
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.auto_awesome, color: _connected ? Colors.greenAccent : Colors.orangeAccent),
          const SizedBox(width: 8),
          const Expanded(child: Text('GEMINI SIGNAL REVIEW', style: TextStyle(fontWeight: FontWeight.w900))),
          Text(_connected ? 'CONNECTED' : 'NOT VERIFIED',
              style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900,
                  color: _connected ? Colors.greenAccent : Colors.orangeAccent)),
        ]),
        const SizedBox(height: 4),
        Text('${widget.selectedIndex} • $_model', style: const TextStyle(fontSize: 11, color: Colors.white70)),
        const SizedBox(height: 8),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: _busy ? null : _review,
            icon: _busy
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.fact_check_outlined),
            label: Text(_busy ? 'REVIEWING WITH GEMINI…' : 'REVIEW CURRENT SIGNAL WITH GEMINI'),
          ),
        ),
        if (_error != null) Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(_error!, style: const TextStyle(color: Colors.redAccent, fontSize: 12)),
        ),
        if (_answer != null) Padding(
          padding: const EdgeInsets.only(top: 8),
          child: SelectableText(_answer!, style: const TextStyle(fontSize: 12)),
        ),
        const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text(
            'Advisory only. This review cannot override backend validation or change the final WAIT/PASS decision.',
            style: TextStyle(fontSize: 10, color: Colors.white60),
          ),
        ),
      ]),
    ),
  );
}
