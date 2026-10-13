import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:webview_flutter/webview_flutter.dart';

/// Uses the user-supplied HTML footprint chart unchanged in layout and controls.
/// Demo prices are never generated in Flutter; only the configured backend WS is used.
class OrderFlowPage extends StatefulWidget {
  const OrderFlowPage({required this.signalBackendUrl, super.key});
  final String signalBackendUrl;

  @override
  State<OrderFlowPage> createState() => _OrderFlowPageState();
}

class _OrderFlowPageState extends State<OrderFlowPage> {
  late final WebViewController _controller;
  bool _loading = true;
  String? _error;

  Uri get _webSocketBase {
    final base = Uri.parse(widget.signalBackendUrl.trim());
    return base.replace(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      path: '/ws',
      queryParameters: const <String, String>{},
      fragment: '',
    );
  }

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF0B0F14));
    _loadChart();
  }

  @override
  void didUpdateWidget(covariant OrderFlowPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.signalBackendUrl != widget.signalBackendUrl) {
      _loadChart();
    }
  }

  Future<void> _loadChart() async {
    try {
      setState(() {
        _loading = true;
        _error = null;
      });
      var html = await rootBundle.loadString('assets/order_flow_footprint.html');
      html = html.replaceAll('__FOOTPRINT_WS_URL__', _webSocketBase.toString());
      await _controller.loadHtmlString(
        html,
        baseUrl: widget.signalBackendUrl.trim(),
      );
      if (mounted) setState(() => _loading = false);
    } catch (error) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = 'Footprint chart could not load: $error';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0F14),
      body: SafeArea(
        child: Stack(
          children: [
            WebViewWidget(controller: _controller),
            if (_loading)
              const Positioned.fill(
                child: ColoredBox(
                  color: Color(0xFF0B0F14),
                  child: Center(child: CircularProgressIndicator()),
                ),
              ),
            if (_error != null)
              Positioned.fill(
                child: ColoredBox(
                  color: const Color(0xFF0B0F14),
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.error_outline, color: Colors.orangeAccent, size: 34),
                          const SizedBox(height: 12),
                          Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70)),
                          const SizedBox(height: 12),
                          FilledButton.icon(
                            onPressed: _loadChart,
                            icon: const Icon(Icons.refresh),
                            label: const Text('Retry chart'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
