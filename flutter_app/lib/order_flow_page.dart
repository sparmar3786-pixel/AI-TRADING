import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';

class OrderFlowPage extends StatefulWidget {
  const OrderFlowPage({required this.backendUrl, required this.signalBackendUrl, super.key});
  final String backendUrl;
  final String signalBackendUrl;
  @override
  State<OrderFlowPage> createState() => _OrderFlowPageState();
}

class _OrderFlowPageState extends State<OrderFlowPage> {
  static const cyan = Color(0xFF12D6FF), green = Color(0xFF26C281), red = Color(0xFFEF4B5B);
  final symbols = const ['NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY','SENSEX','BANKEX'];
  String symbol = 'NIFTY', status = 'CONNECTING', error = '';
  WebSocket? socket;
  Timer? retry;
  bool disposed = false;
  List<Map<String,dynamic>> candles = [];
  double numv(dynamic v) => v is num ? v.toDouble() : double.tryParse('$v') ?? 0;

  Uri get uri {
    final base = Uri.parse(widget.signalBackendUrl);
    return base.replace(scheme: base.scheme == 'https' ? 'wss' : 'ws', path: '/ws', queryParameters: {'symbol': symbol});
  }

  @override
  void initState() { super.initState(); connect(); }

  Future<void> connect() async {
    retry?.cancel();
    await socket?.close();
    if (disposed) return;
    setState(() { status = 'CONNECTING'; error = ''; });
    try {
      final ws = await WebSocket.connect(uri.toString()).timeout(const Duration(seconds: 8));
      if (disposed) { await ws.close(); return; }
      socket = ws;
      ws.listen((event) {
        try {
          final msg = jsonDecode(event as String);
          if (msg is! Map) return;
          final next = List<Map<String,dynamic>>.from(candles);
          if (msg['type'] == 'snap' && msg['candles'] is List) {
            next..clear()..addAll((msg['candles'] as List).whereType<Map>().map((e) => Map<String,dynamic>.from(e)));
          } else if (msg['candle'] is Map) {
            final c = Map<String,dynamic>.from(msg['candle'] as Map);
            final i = next.indexWhere((e) => e['t'] == c['t']);
            if (i >= 0) { next[i] = c; } else { next.add(c); }
            next.sort((a,b) => numv(a['t']).compareTo(numv(b['t'])));
            if (next.length > 250) next.removeRange(0, next.length - 250);
          }
          if (mounted) setState(() { candles = next; status = (msg['mode'] ?? 'CONNECTED').toString().toUpperCase(); error = ''; });
        } catch (_) { if (mounted) setState(() => error = 'Backend order-flow message could not be parsed.'); }
      }, onDone: scheduleRetry, onError: (_) { if (mounted) setState(() => status = 'DISCONNECTED'); scheduleRetry(); });
    } catch (_) {
      if (mounted) setState(() { status = 'DISCONNECTED'; error = 'Backend WebSocket /ws is unavailable. No demo prices are displayed.'; });
      scheduleRetry();
    }
  }

  void scheduleRetry() {
    if (disposed) return;
    retry?.cancel();
    retry = Timer(const Duration(seconds: 3), connect);
  }

  @override
  void dispose() { disposed = true; retry?.cancel(); socket?.close(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final last = candles.isEmpty ? null : candles.last;
    final isLive = status == 'LIVE';
    return Scaffold(
      backgroundColor: const Color(0xFF070B12),
      body: SafeArea(child: Column(children: [
        Padding(padding: const EdgeInsets.all(12), child: Row(children: [
          const Icon(Icons.multiline_chart, color: cyan), const SizedBox(width: 8),
          const Expanded(child: Text('ORDER FLOW', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1))),
          Container(padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5), decoration: BoxDecoration(color: isLive ? const Color(0xFF123D2E) : const Color(0xFF3A2B14), borderRadius: BorderRadius.circular(20)),
            child: Text(status, style: TextStyle(color: isLive ? green : Colors.orangeAccent, fontSize: 10, fontWeight: FontWeight.bold))),
        ])),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: Row(children: [
          Expanded(child: DropdownButtonFormField<String>(value: symbol, dropdownColor: const Color(0xFF101722), items: symbols.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(), onChanged: (s) { if (s != null) setState(() { symbol = s; candles = []; }); connect(); })),
          const SizedBox(width: 8), IconButton(onPressed: connect, icon: const Icon(Icons.refresh, color: cyan)),
        ])),
        if (error.isNotEmpty) Padding(padding: const EdgeInsets.all(12), child: Text(error, style: const TextStyle(color: Colors.orangeAccent))),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: Row(children: [
          metric('LTP', last == null ? '—' : numv(last['c']).toStringAsFixed(2)),
          metric('DELTA', last == null ? '—' : numv(last['d']).toStringAsFixed(0), numv(last?['d'] ?? 0) >= 0 ? green : red),
          metric('DEPTH', last == null ? '—' : numv(last['v']).toStringAsFixed(0)),
        ])),
        const SizedBox(height: 8),
        Expanded(child: Container(margin: const EdgeInsets.all(10), decoration: BoxDecoration(color: const Color(0xFF101722), border: Border.all(color: const Color(0xFF123B59)), borderRadius: BorderRadius.circular(12)),
          child: candles.isEmpty
            ? const Center(child: Padding(padding: EdgeInsets.all(24), child: Text('Waiting for backend order-flow data.\n\nNo sample prices are shown. Backend must expose /ws?symbol=…', textAlign: TextAlign.center, style: TextStyle(color: Colors.white70))))
            : CustomPaint(painter: FootprintPainter(candles), child: const SizedBox.expand()))),
        const Padding(padding: EdgeInsets.fromLTRB(12, 0, 12, 12), child: Text('Live status requires a fresh broker timestamp. Depth and delta are bid/ask book quantities, not classified exchange trade volume.', style: TextStyle(color: Colors.white54, fontSize: 10))),
      ])),
    );
  }

  Widget metric(String label, String value, [Color color = Colors.white]) => Expanded(child: Container(
    margin: const EdgeInsets.only(right: 6), padding: const EdgeInsets.all(9),
    decoration: BoxDecoration(color: const Color(0xFF101722), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF17354D))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(label, style: const TextStyle(color: Colors.white54, fontSize: 10)), const SizedBox(height: 4), Text(value, style: TextStyle(color: color, fontWeight: FontWeight.bold))])));
}

class FootprintPainter extends CustomPainter {
  FootprintPainter(this.candles);
  final List<Map<String,dynamic>> candles;
  double n(dynamic v) => v is num ? v.toDouble() : double.tryParse('$v') ?? 0;
  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty || size.width <= 0 || size.height <= 0) return;
    final vis = candles.length > 32 ? candles.sublist(candles.length - 32) : candles;
    final lows = vis.map((c) => n(c['l'])).toList(), highs = vis.map((c) => n(c['h'])).toList();
    final lo = lows.reduce((a,b) => a < b ? a : b), hi = highs.reduce((a,b) => a > b ? a : b);
    final range = (hi - lo).abs() < .001 ? 1.0 : hi - lo;
    const top = 24.0, bottomGap = 35.0;
    final plotH = size.height - top - bottomGap, cw = size.width / vis.length;
    final grid = Paint()..color = const Color(0xFF203040)..strokeWidth = .5;
    for (var j=0; j<6; j++) { final y=top+plotH*j/5; canvas.drawLine(Offset(0,y),Offset(size.width,y),grid); }
    for (var i=0; i<vis.length; i++) {
      final c=vis[i]; double y(double p)=>top+(hi-p)/range*plotH;
      final o=n(c['o']), h=n(c['h']), l=n(c['l']), close=n(c['c']);
      final color=close>=o?const Color(0xFF26C281):const Color(0xFFEF4B5B);
      final p=Paint()..color=color;
      canvas.drawLine(Offset(i*cw+cw/2,y(h)),Offset(i*cw+cw/2,y(l)),p..strokeWidth=1.2);
      final yo=y(o), yc=y(close);
      canvas.drawRect(Rect.fromLTRB(i*cw+cw*.2, yo<yc?yo:yc, i*cw+cw*.8, (yo-yc).abs()<2?(yo<yc?yo:yc)+2:(yo>yc?yo:yc)),p);
    }
    final tp=TextPainter(textDirection: TextDirection.ltr)..text=TextSpan(text:'Broker snapshots: '+vis.length.toString()+'   •   High '+hi.toStringAsFixed(2)+'   Low '+lo.toStringAsFixed(2),style:const TextStyle(color:Color(0xFF12D6FF),fontSize:11));
    tp.layout(maxWidth:size.width); tp.paint(canvas,const Offset(8,6));
  }
  @override
  bool shouldRepaint(covariant FootprintPainter oldDelegate) => oldDelegate.candles != candles;
}
