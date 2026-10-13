import 'package:flutter/material.dart';

/// Calculates a transparent, user-checkable estimate from a live LTP and
/// contract size. It deliberately never guesses lot sizes when metadata is absent.
class RiskCalculator extends StatefulWidget {
  const RiskCalculator({
    required this.selectedIndex,
    required this.marketByIndex,
    required this.commodities,
    super.key,
  });

  final String selectedIndex;
  final Map<String, dynamic> marketByIndex;
  final List<dynamic> commodities;

  @override
  State<RiskCalculator> createState() => _RiskCalculatorState();
}

class _RiskCalculatorState extends State<RiskCalculator> {
  static const _indices = <String>[
    'NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX',
  ];
  late String _symbol;
  String _side = 'BUY';
  final _entry = TextEditingController();
  final _stop = TextEditingController();
  final _target = TextEditingController();
  final _lots = TextEditingController(text: '1');
  final _lotSize = TextEditingController();
  final _optionLtp = TextEditingController(text: '220');
  final _premiumPointSl = TextEditingController(text: '5');
  final _premiumRupeeSl = TextEditingController(text: '30');
  final _thetaPerDay = TextEditingController(text: '2');

  @override
  void initState() {
    super.initState();
    _symbol = widget.selectedIndex;
    _seedFromQuote();
    for (final c in [_entry, _stop, _target, _lots, _lotSize, _optionLtp, _premiumPointSl, _premiumRupeeSl, _thetaPerDay]) {
      c.addListener(_changed);
    }
  }

  @override
  void didUpdateWidget(covariant RiskCalculator oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selectedIndex != widget.selectedIndex && _indices.contains(widget.selectedIndex)) {
      _symbol = widget.selectedIndex;
      _entry.clear();
      _stop.clear();
      _target.clear();
      _lotSize.clear();
      _seedFromQuote();
    }
  }

  Map<String, dynamic> _row(String symbol) {
    final indexRow = widget.marketByIndex[symbol];
    if (indexRow is Map) return Map<String, dynamic>.from(indexRow);
    for (final item in widget.commodities) {
      if (item is! Map) continue;
      final row = Map<String, dynamic>.from(item);
      final name = (row['name'] ?? row['symbol'] ?? '').toString().toUpperCase();
      final code = (row['symbol'] ?? row['name'] ?? '').toString().toUpperCase();
      if (name == symbol || code == symbol || code.startsWith('${symbol}')) return row;
    }
    return <String, dynamic>{};
  }

  double? _num(dynamic value) {
    if (value is num && value.isFinite) return value.toDouble();
    if (value == null) return null;
    return double.tryParse(value.toString().replaceAll(',', '').trim());
  }

  double? _firstNum(Map<String, dynamic> row, List<String> keys) {
    for (final key in keys) {
      final value = _num(row[key]);
      if (value != null && value > 0) return value;
    }
    return null;
  }

  void _seedFromQuote() {
    final row = _row(_symbol);
    final ltp = _firstNum(row, ['ltp', 'last_price', 'lastPrice', 'close']);
    if (ltp != null && !_indices.contains(_symbol)) {
      _entry.text = ltp.toStringAsFixed(2);
    }
    final size = _firstNum(row, [
      'lot_size', 'lotSize', 'lotsize', 'quantity_per_lot',
      'contract_size', 'trade_quantity',
    ]);
    if (size != null) _lotSize.text = size.toStringAsFixed(size == size.roundToDouble() ? 0 : 2);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    for (final c in [_entry, _stop, _target, _lots, _lotSize, _optionLtp, _premiumPointSl, _premiumRupeeSl, _thetaPerDay]) {
      c.removeListener(_changed);
      c.dispose();
    }
    super.dispose();
  }

  Widget _field(String label, TextEditingController controller, {String? hint}) =>
      SizedBox(
        width: 145,
        child: TextField(
          controller: controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: label, hintText: hint, isDense: true),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final row = _row(_symbol);
    final ltp = _firstNum(row, ['ltp', 'last_price', 'lastPrice', 'close']);
    final age = _num(row['age_seconds'] ?? row['tick_age_seconds']);
    final fresh = ltp != null && age != null && age >= 0 && age <= 60 &&
        (row['live'] == true || row['data_fresh'] == true);
    final entry = _num(_entry.text);
    final stop = _num(_stop.text);
    final target = _num(_target.text);
    final lotsRaw = _num(_lots.text);
    final lotSize = _num(_lotSize.text);
    final lots = lotsRaw != null && lotsRaw > 0 && lotsRaw == lotsRaw.roundToDouble()
        ? lotsRaw.toInt() : null;
    final qty = lots != null && lotSize != null && lotSize > 0 ? lots * lotSize : null;
    final isBuy = _side == 'BUY';
    final optionLtp = _num(_optionLtp.text);
    final premiumPointSl = _num(_premiumPointSl.text);
    final premiumRupeeSl = _num(_premiumRupeeSl.text);
    final thetaPerDay = _num(_thetaPerDay.text);
    final premiumSlByPoints = optionLtp != null && premiumPointSl != null && premiumPointSl > 0 ? optionLtp - premiumPointSl : null;
    final premiumPointsByRupees = optionLtp != null && premiumRupeeSl != null && premiumRupeeSl > 0 ? optionLtp - premiumRupeeSl : null;
    final rupeeRiskByPoints = qty != null && premiumPointSl != null && premiumPointSl > 0 ? qty * premiumPointSl : null;
    final pointsByRupeeRisk = qty != null && premiumRupeeSl != null && premiumRupeeSl > 0 ? premiumRupeeSl / qty : null;
    final oneDayThetaEstimate = thetaPerDay != null && thetaPerDay > 0 ? thetaPerDay : null;
    final targetPoints = entry != null && target != null ? (target - entry) * (isBuy ? 1 : -1) : null;
    final stopPoints = entry != null && stop != null ? (entry - stop) * (isBuy ? 1 : -1) : null;
    final targetValid = targetPoints != null && targetPoints > 0;
    final stopValid = stopPoints != null && stopPoints > 0;
    final targetPnl = targetValid && qty != null ? targetPoints * qty : null;
    final stopPnl = stopValid && qty != null ? -stopPoints * qty : null;
    final livePnl = !_indices.contains(_symbol) && ltp != null && entry != null && qty != null
        ? (ltp - entry) * qty * (isBuy ? 1 : -1) : null;
    final currency = (double? value) => value == null
        ? '—'
        : '₹${value.toStringAsFixed(2)}';
    final points = (double? value) => value == null ? '—' : '${value.toStringAsFixed(2)} pts';
    final symbols = <String>{..._indices, ...widget.commodities.map((item) {
      if (item is! Map) return '';
      final row = Map<String, dynamic>.from(item);
      return (row['name'] ?? row['symbol'] ?? '').toString().toUpperCase();
    }).where((s) => s.isNotEmpty)}.toList();
    if (!symbols.contains(_symbol)) symbols.insert(0, _symbol);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('LIVE INDEX + MCX RISK CALCULATOR',
              style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: .5)),
          const SizedBox(height: 4),
          const Text('Calculations use price points × lots × contract quantity. Index spot is reference-only; enter the traded contract price and verified lot size. Lot size is never guessed.',
              style: TextStyle(fontSize: 11, color: Colors.white70)),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            value: symbols.contains(_symbol) ? _symbol : symbols.first,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Index / MCX contract', isDense: true),
            items: symbols.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
            onChanged: (value) {
              if (value == null) return;
              setState(() {
                _symbol = value;
                _entry.clear();
                _stop.clear();
                _target.clear();
                _lotSize.clear();
                _seedFromQuote();
              });
            },
          ),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: Text('LTP: ${ltp == null ? 'NO LIVE QUOTE' : '₹${ltp.toStringAsFixed(2)}'}',
                style: TextStyle(fontWeight: FontWeight.w800, color: fresh ? Colors.greenAccent : Colors.redAccent))),
            Text(fresh ? 'FRESH' : 'NOT VERIFIED LIVE',
                style: TextStyle(fontSize: 10, color: fresh ? Colors.greenAccent : Colors.orangeAccent)),
          ]),
          Text('Source: ${row['source'] ?? row['feed_mode'] ?? 'unknown'} • Quote age: ${age == null ? 'unknown' : '${age.toStringAsFixed(1)}s'}',
              style: const TextStyle(fontSize: 10, color: Colors.white60)),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            value: _side,
            decoration: const InputDecoration(labelText: 'Position direction', isDense: true),
            items: const [
              DropdownMenuItem(value: 'BUY', child: Text('BUY / LONG')),
              DropdownMenuItem(value: 'SELL', child: Text('SELL / SHORT')),
            ],
            onChanged: (value) => setState(() => _side = value ?? 'BUY'),
          ),
          const SizedBox(height: 8),
          Wrap(spacing: 10, runSpacing: 8, children: [
            _field('Entry / traded contract LTP', _entry, hint: 'Actual contract price'),
            _field('Stop loss LTP', _stop, hint: 'SL price'),
            _field('Target LTP', _target, hint: 'Target price'),
            _field('Lots', _lots, hint: '1'),
            _field('Qty per lot', _lotSize, hint: 'Verified lot size'),
          ]),
          const Divider(height: 22),
          const Text('OPTION PREMIUM STOP-LOSS • POINTS + RUPEES', style: TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF12D6FF))),
          const SizedBox(height: 6),
          Wrap(spacing: 10, runSpacing: 8, children: [
            _field('Option premium LTP', _optionLtp, hint: '220'),
            _field('SL distance (premium pts)', _premiumPointSl, hint: '5'),
            _field('Max loss per unit (₹)', _premiumRupeeSl, hint: '30'),
            _field('Theta (₹/unit/day)', _thetaPerDay, hint: 'from live Greeks'),
          ]),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            _metric('5-point SL premium', premiumSlByPoints == null || premiumSlByPoints <= 0 ? '—' : '₹${premiumSlByPoints.toStringAsFixed(2)}'),
            _metric('₹30-risk SL premium', premiumPointsByRupees == null || premiumPointsByRupees <= 0 ? '—' : '₹${premiumPointsByRupees.toStringAsFixed(2)}'),
            _metric('Loss at point SL', currency(rupeeRiskByPoints), color: Colors.redAccent),
            _metric('Points for rupee risk', points(pointsByRupeeRisk)),
            _metric('1-day theta estimate', currency(oneDayThetaEstimate), color: Colors.orangeAccent),
          ]),
          const Text('Example: option LTP ₹220, 5 premium-point SL → SL premium ₹215. With quantity 50, estimated loss = ₹250 before costs. A ₹30 premium drop gives SL premium ₹190; loss per unit is ₹30 (₹1,500 for quantity 50). Enter verified live theta; theta is not constant and decay accelerates near expiry. Delta, gamma, IV/vega, spread, liquidity and directional move also change option premium.', style: TextStyle(fontSize: 11, color: Colors.white70)),
          const Divider(height: 22),
          Wrap(spacing: 8, runSpacing: 8, children: [
            _metric('Quantity', qty == null ? 'Enter lot size' : qty.toStringAsFixed(qty == qty.roundToDouble() ? 0 : 2)),
            _metric('Target distance', points(targetValid ? targetPoints : null)),
            _metric('SL distance', points(stopValid ? stopPoints : null)),
            _metric('Potential profit', currency(targetPnl), color: Colors.greenAccent),
            _metric('Potential loss', currency(stopPnl), color: Colors.redAccent),
            _metric('Current contract P&L', currency(livePnl), color: livePnl == null ? null : livePnl >= 0 ? Colors.greenAccent : Colors.redAccent),
          ]),
          const SizedBox(height: 6),
          Text(
            ltp == null ? 'Live LTP unavailable. Enter a verified entry price; do not treat cached or missing data as live.' :
            (qty == null ? 'Enter the verified contract quantity per lot to calculate ₹ P&L.' :
            ((!targetValid || !stopValid) ? 'Set target and stop loss on the correct side of entry to calculate risk.' :
            'Estimate only. Excludes brokerage, taxes, slippage, gaps and contract-specific margin.')),
            style: const TextStyle(fontSize: 11, color: Colors.orangeAccent),
          ),
        ]),
      ),
    );
  }

  Widget _metric(String label, String value, {Color? color}) => Container(
    width: 145,
    padding: const EdgeInsets.all(9),
    decoration: BoxDecoration(
      color: const Color(0xFF111923),
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: const Color(0xFF263442)),
    ),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(fontSize: 10, color: Colors.white60)),
      const SizedBox(height: 3),
      Text(value, style: TextStyle(fontWeight: FontWeight.w800, color: color)),
    ]),
  );
}
