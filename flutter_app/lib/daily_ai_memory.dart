import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Phone-local, day-partitioned AI market memory.
///
/// Files live in the app-specific Android files directory (no broad storage
/// permission required): AI-TRADING/AI-Memory/YYYY-MM-DD.json. This stores
/// observed backend data only; it never fabricates candles, OI, or book depth.
class DailyAiMemory {
  static String? lastWritePath;
  static String? lastWriteError;
  static String? _lastMinuteKey;

  static Future<Directory> _memoryDirectory() async {
    final base = await getExternalStorageDirectory() ?? await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/AI-TRADING/AI-Memory');
    await dir.create(recursive: true);
    return dir;
  }

  static String _dayKey(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';

  static String _minuteKey(DateTime date) =>
      '${_dayKey(date)}T${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';

  static double? _num(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }

  static Map<String, dynamic> _map(dynamic value) =>
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

  static Map<String, dynamic> _oiAnalysis(
    List<dynamic> currentRows,
    List<dynamic> previousRows,
  ) {
    final previousByToken = <String, Map<String, dynamic>>{};
    for (final row in previousRows) {
      final item = _map(row);
      final token = (item['token'] ?? item['symbol'] ?? '').toString();
      if (token.isNotEmpty) previousByToken[token] = item;
    }
    final events = <Map<String, dynamic>>[];
    for (final row in currentRows) {
      final item = _map(row);
      final token = (item['token'] ?? item['symbol'] ?? '').toString();
      final previous = previousByToken[token];
      final oi = _num(item['oi']);
      final oldOi = _num(previous?['oi']);
      final ltp = _num(item['ltp']);
      final oldLtp = _num(previous?['ltp']);
      final oiDelta = _num(item['oi_change']) ?? (oi != null && oldOi != null ? oi - oldOi : null);
      final priceDelta = ltp != null && oldLtp != null ? ltp - oldLtp : null;
      String? classification;
      if (oiDelta != null && priceDelta != null) {
        if (oiDelta > 0 && priceDelta > 0) classification = 'LONG_BUILDUP';
        if (oiDelta > 0 && priceDelta < 0) classification = 'SHORT_BUILDUP';
        if (oiDelta < 0 && priceDelta > 0) classification = 'SHORT_COVERING';
        if (oiDelta < 0 && priceDelta < 0) classification = 'LONG_UNWINDING';
      }
      events.add({
        'token': token,
        'symbol': item['symbol'],
        'side': item['side'] ?? item['option_type'],
        'strike': item['strike'],
        'expiry': item['expiry'],
        'timestamp': item['source_timestamp'] ?? item['timestamp'],
        'ltp': ltp,
        'price_change': priceDelta,
        'oi': oi,
        'oi_change': oiDelta,
        'classification': classification ?? 'INSUFFICIENT_PRIOR_SNAPSHOT',
      });
    }
    return {
      'method': 'price_change_and_open_interest_change',
      'note': 'OI classifications require two timestamped observations; missing history is not inferred.',
      'events': events,
    };
  }

  static Future<void> saveSnapshot({
    required Map<String, dynamic> market,
    required Map<String, dynamic> signals,
    required List<dynamic> commodities,
    required Map<String, List<dynamic>> optionChains,
  }) async {
    final now = DateTime.now();
    final minuteKey = _minuteKey(now);
    // Refresh can run repeatedly in the same minute. Replace that minute's
    // latest observation instead of filling storage with duplicate polls.
    if (_lastMinuteKey == minuteKey) return;
    _lastMinuteKey = minuteKey;

    try {
      final dir = await _memoryDirectory();
      final path = '${dir.path}/${_dayKey(now)}.json';
      final file = File(path);
      List<dynamic> snapshots = <dynamic>[];
      if (await file.exists()) {
        try {
          final decoded = jsonDecode(await file.readAsString());
          if (decoded is Map && decoded['snapshots'] is List) {
            snapshots = List<dynamic>.from(decoded['snapshots'] as List);
          }
        } catch (_) {
          // Preserve the damaged file before starting a clean valid journal.
          final backup = File('$path.corrupt-${now.millisecondsSinceEpoch}');
          await file.copy(backup.path);
          snapshots = <dynamic>[];
        }
      }

      final previous = snapshots.isNotEmpty ? _map(snapshots.last) : <String, dynamic>{};
      final previousChains = _map(previous['option_chains']);
      final chainAnalysis = <String, dynamic>{};
      final chainPayload = <String, dynamic>{};
      for (final entry in optionChains.entries) {
        final rows = List<dynamic>.from(entry.value);
        chainPayload[entry.key] = rows;
        chainAnalysis[entry.key] = _oiAnalysis(rows, List<dynamic>.from(previousChains[entry.key] as List? ?? const []));
      }

      final marketAnalysis = <String, dynamic>{};
      for (final entry in market.entries) {
        final row = _map(entry.value);
        final signal = _map(signals[entry.key]);
        final indicators = _map(signal['indicators'] ?? row['indicators']);
        marketAnalysis[entry.key] = {
          'source': row['source'] ?? signal['data_source'],
          'source_timestamp': row['source_timestamp'] ?? row['timestamp'],
          'live': row['live'] == true,
          'ltp': row['ltp'],
          'age_seconds': row['age_seconds'],
          'decision': signal['decision'] ?? 'WAIT',
          'reasons': signal['reasons'] ?? signal['reason'] ?? const [],
          'support': indicators['support'] ?? signal['support'] ?? row['support'],
          'resistance': indicators['resistance'] ?? signal['resistance'] ?? row['resistance'],
          'day_high': row['day_high'] ?? indicators['day_high'],
          'day_low': row['day_low'] ?? indicators['day_low'],
          'indicators': indicators,
        };
      }

      snapshots.add({
        'saved_at': now.toIso8601String(),
        'minute_key': minuteKey,
        'source': 'AI-TRADING observed API snapshot',
        'market_analysis': marketAnalysis,
        'signals': signals,
        'commodities': commodities,
        'option_chains': chainPayload,
        'oi_analysis': chainAnalysis,
      });
      if (snapshots.length > 6000) snapshots = snapshots.sublist(snapshots.length - 6000);
      final document = {
        'schema_version': 1,
        'date': _dayKey(now),
        'timezone': 'device-local',
        'storage_note': 'App-specific phone storage. Only observed API data is saved.',
        'snapshot_count': snapshots.length,
        'snapshots': snapshots,
      };
      await file.writeAsString(jsonEncode(document), flush: true);
      lastWritePath = path;
      lastWriteError = null;
    } catch (error) {
      lastWriteError = error.toString();
    }
  }

  static Future<Map<String, dynamic>> readDay(DateTime date) async {
    try {
      final dir = await _memoryDirectory();
      final file = File('${dir.path}/${_dayKey(date)}.json');
      if (!await file.exists()) return <String, dynamic>{'date': _dayKey(date), 'snapshots': <dynamic>[]};
      final decoded = jsonDecode(await file.readAsString());
      return decoded is Map ? Map<String, dynamic>.from(decoded) : <String, dynamic>{};
    } catch (error) {
      return <String, dynamic>{'error': error.toString(), 'snapshots': <dynamic>[]};
    }
  }
}
