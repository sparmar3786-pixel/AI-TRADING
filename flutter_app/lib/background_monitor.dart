import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'config.dart';

const _serviceChannelId = 'ai_trading_background_monitor';
const _alertChannelId = 'ai_trading_qualified_setups';
const _serviceNotificationId = 7831;

final FlutterLocalNotificationsPlugin _notifications = FlutterLocalNotificationsPlugin();

Future<void> initializeBackgroundMonitor() async {
  if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return;
  try {
    const initialization = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    );
    await _notifications.initialize(initialization);
    final android = _notifications.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    await android?.createNotificationChannel(const AndroidNotificationChannel(
      _serviceChannelId,
      'AI-TRADING live monitor',
      description: 'Keeps qualified setup monitoring available in the background.',
      importance: Importance.low,
      playSound: false,
    ));
    await android?.createNotificationChannel(const AndroidNotificationChannel(
      _alertChannelId,
      'Qualified trading setup alerts',
      description: 'Audible alerts only when every deterministic setup gate passes.',
      importance: Importance.max,
      playSound: true,
    ));
    await android?.requestNotificationsPermission();

    final service = FlutterBackgroundService();
    await service.configure(
      androidConfiguration: AndroidConfiguration(
        onStart: aiTradingBackgroundStart,
        autoStart: true,
        autoStartOnBoot: true,
        isForegroundMode: true,
        notificationChannelId: _serviceChannelId,
        initialNotificationTitle: 'AI-TRADING live monitor',
        initialNotificationContent: 'Checking live data and qualified setups',
        foregroundServiceNotificationId: _serviceNotificationId,
        foregroundServiceTypes: [AndroidForegroundType.dataSync],
      ),
      iosConfiguration: IosConfiguration(
        autoStart: false,
        onForeground: aiTradingBackgroundStart,
        onBackground: aiTradingIosBackground,
      ),
    );
    if (!await service.isRunning()) {
      await service.startService();
    }
  } catch (error) {
    // A background-service permission/device-policy issue must not prevent the
    // main trading UI from opening. Surface the reason in logcat for diagnosis.
    debugPrint('AI_TRADING_BACKGROUND_INIT_FAILED: $error');
  }
}

@pragma('vm:entry-point')
Future<bool> aiTradingIosBackground(ServiceInstance service) async {
  DartPluginRegistrant.ensureInitialized();
  return true;
}

@pragma('vm:entry-point')
void aiTradingBackgroundStart(ServiceInstance service) async {
  DartPluginRegistrant.ensureInitialized();
  final notifications = FlutterLocalNotificationsPlugin();
  await notifications.initialize(const InitializationSettings(
    android: AndroidInitializationSettings('@mipmap/ic_launcher'),
  ));
  if (service is AndroidServiceInstance) {
    await service.setAsForegroundService();
  }
  service.on('stopService').listen((_) => service.stopSelf());

  var polling = false;
  Timer.periodic(const Duration(seconds: 25), (timer) async {
    if (polling) return;
    polling = true;
    try {
      await _pollQualifiedSetups(notifications);
      if (service is AndroidServiceInstance) {
        await service.setForegroundNotificationInfo(
          title: 'AI-TRADING live monitor',
          content: 'Monitoring live quotes • last check ${DateTime.now().toLocal().toString().substring(11, 19)}',
        );
      }
    } catch (error) {
      debugPrint('AI_TRADING_BACKGROUND_POLL_FAILED: ${error.runtimeType}');
    } finally {
      polling = false;
    }
  });
}

Future<void> _pollQualifiedSetups(FlutterLocalNotificationsPlugin notifications) async {
  final prefs = await SharedPreferences.getInstance();
  var deviceId = prefs.getString('fresh_device_id') ?? '';
  if (deviceId.length < 43) {
    deviceId = base64UrlEncode(List<int>.generate(32, (_) => Random.secure().nextInt(256))).replaceAll('=', '');
    await prefs.setString('fresh_device_id', deviceId);
  }
  final base = AppConfig.signalBackendUrl.replaceAll(RegExp(r'/+$'), '');
  final uri = Uri.parse('$base/v1/signals');
  final headers = <String, String>{
    'accept': 'application/json',
    'X-Device-Id': deviceId,
  };
  final accessKey = await FreshApi.readSavedBackendAccessKey();
  if (accessKey != null) headers['X-API-Access-Key'] = accessKey;
  final response = await http.get(uri, headers: headers)
      .timeout(const Duration(seconds: 18));
  if (response.statusCode != 200) return;
  final decoded = jsonDecode(response.body);
  if (decoded is! Map) return;
  final rawSignals = decoded['signals'];
  if (rawSignals is! Map) return;

  final prior = prefs.getStringList('ai_trading_alerted_setups') ?? <String>[];
  final seen = prior.toSet();
  var changed = false;
  for (final entry in rawSignals.entries) {
    if (entry.value is! Map) continue;
    final row = Map<String, dynamic>.from(entry.value as Map);
    final decision = (row['decision'] ?? '').toString().toUpperCase();
    if (decision != 'CALL BUY' && decision != 'PUT BUY') continue;
    if (row['data_fresh'] != true) continue;
    final validation = Map<String, dynamic>.from(row['live_validation'] as Map? ?? const {});
    if (validation['verdict'] != 'PASS') continue;
    final stability = Map<String, dynamic>.from(row['signal_stability'] as Map? ?? const {});
    if (stability['state'] != 'CONFIRMED') continue;
    final engine = Map<String, dynamic>.from(
      row['five_layer_engine'] as Map? ?? row['quant_engine'] as Map? ?? const {},
    );
    final layers = Map<String, dynamic>.from(engine['layers'] as Map? ?? const {});
    if (layers.length < 5 || layers.values.any((layer) => layer is! Map || layer['pass'] != true)) continue;
    final strike = row['strike'] ?? '';
    final entryPrice = row['entry'] ?? '';
    final stamp = row['source_timestamp'] ?? row['timestamp'] ?? decoded['generated_at'] ?? '';
    final key = '${entry.key}|$decision|$strike|$entryPrice|$stamp';
    if (seen.contains(key)) continue;

    // Ask NVIDIA only for a new, deterministic PASS candidate, and throttle
    // repeated review attempts for the same setup to avoid request storms.
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    Map<String, int> cooldowns = <String, int>{};
    try {
      final decodedCooldowns = jsonDecode(prefs.getString('ai_trading_review_cooldowns') ?? '{}');
      if (decodedCooldowns is Map) {
        cooldowns = decodedCooldowns.map((key, value) =>
            MapEntry(key.toString(), int.tryParse(value.toString()) ?? 0));
      }
    } catch (_) {}
    final lastReview = cooldowns[key] ?? 0;
    if (nowMs - lastReview < 120000) continue;
    cooldowns[key] = nowMs;
    if (cooldowns.length > 50) {
      final ordered = cooldowns.entries.toList()..sort((a, b) => a.value.compareTo(b.value));
      for (final old in ordered.take(cooldowns.length - 50)) {
        cooldowns.remove(old.key);
      }
    }
    await prefs.setString('ai_trading_review_cooldowns', jsonEncode(cooldowns));
    final reviewResponse = await http.post(
      Uri.parse('$base/v1/ai/review-signal'),
      headers: {'accept': 'application/json', 'content-type': 'application/json', 'X-Device-Id': deviceId},
      body: jsonEncode({'index': entry.key}),
    ).timeout(const Duration(seconds: 40));
    if (reviewResponse.statusCode != 200) continue;
    final reviewJson = jsonDecode(reviewResponse.body);
    if (reviewJson is! Map ||
        reviewJson['verdict'] != 'PASS' ||
        reviewJson['decision'] != decision ||
        reviewJson['ai_direction_consistent'] != true) continue;

    seen.add(key);
    changed = true;
    final id = key.hashCode & 0x7fffffff;
    await notifications.show(
      id,
      'Qualified setup • ${entry.key}',
      '$decision • Strike $strike • Entry $entryPrice. All backend validation and risk gates passed.',
      const NotificationDetails(
        android: AndroidNotificationDetails(
          _alertChannelId,
          'Qualified trading setup alerts',
          channelDescription: 'Audible alerts for fully validated setups.',
          importance: Importance.max,
          priority: Priority.high,
          playSound: true,
          category: AndroidNotificationCategory.alarm,
        ),
      ),
      payload: entry.key.toString(),
    );
  }
  if (changed) {
    final values = seen.toList();
    await prefs.setStringList(
      'ai_trading_alerted_setups',
      values.length > 100 ? values.sublist(values.length - 100) : values,
    );
  }
}
