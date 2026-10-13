import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:webview_flutter/webview_flutter.dart';

/// Latest measured WebSocket transport metrics from the original chart.
class OrderFlowTelemetry {
  static Map<String, dynamic> latest = <String, dynamic>{};
  static final List<Map<String, dynamic>> recent = <Map<String, dynamic>>[];

  static void record(String message) {
    try {
      final decoded = jsonDecode(message);
      if (decoded is! Map) return;
      final row = Map<String, dynamic>.from(decoded);
      latest = row;
      recent.insert(0, row);
      if (recent.length > 30) recent.removeRange(30, recent.length);
    } catch (_) {
      // Telemetry is best-effort and must never interrupt the chart.
    }
  }
}

/// Displays the user's original Order Flow HTML without redrawing or restyling
/// its canvas. The HTML connects to the configured signal backend via its
/// document base URL. Demo/sample modes are blocked in the bundled HTML.
class OrderFlowPage extends StatefulWidget {
  const OrderFlowPage({required this.signalBackendUrl, super.key});
  final String signalBackendUrl;

  @override
  State<OrderFlowPage> createState() => _OrderFlowPageState();
}

class _OrderFlowPageState extends State<OrderFlowPage> {
  WebViewController? _controller;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadOriginalChart();
  }

  Future<void> _loadOriginalChart() async {
    try {
      final backend = Uri.parse(widget.signalBackendUrl);
      if (!{'https', 'http'}.contains(backend.scheme) || backend.host.isEmpty) {
        throw StateError('Signal backend URL is invalid.');
      }
      final html = await rootBundle.loadString('assets/order_flow_footprint.html');
      final controller = WebViewController()
        ..setJavaScriptMode(JavaScriptMode.unrestricted)
        ..setBackgroundColor(const Color(0xFF0B0F14))
        ..addJavaScriptChannel('Telemetry', onMessageReceived: (message) {
          OrderFlowTelemetry.record(message.message);
        })
        ..setNavigationDelegate(NavigationDelegate(
          onPageFinished: (_) {
            if (mounted) setState(() => _loading = false);
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame == true && mounted) {
              setState(() {
                _error = 'Order Flow page load failed: ${error.description}';
                _loading = false;
              });
            }
          },
        ));
      if (mounted) setState(() => _controller = controller);
      await controller.loadHtmlString(html, baseUrl: backend.toString());
    } catch (error) {
      if (mounted) setState(() {
        _error = 'Original Order Flow chart could not load: $error';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFF0B0F14),
        body: SafeArea(
          child: Stack(
            children: [
              if (_controller != null) WebViewWidget(controller: _controller!),
              if (_loading)
                const Center(child: CircularProgressIndicator()),
              if (_error != null)
                Center(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Text(
                      _error!,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.orangeAccent),
                    ),
                  ),
                ),
            ],
          ),
        ),
      );
}
