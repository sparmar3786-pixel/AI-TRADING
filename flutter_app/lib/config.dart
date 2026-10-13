class AppConfig {
  // This APK must use its own AI-TRADING Railway service for both general
  // API calls and signal endpoints. Do not silently route general requests to
  // Fresh-Apk's backend: that can mix app state and broker sessions.
  static const String backendUrl = String.fromEnvironment(
    'BACKEND_URL',
    defaultValue: 'https://ai-trading-signals-api-production.up.railway.app',
  );

  static const String signalBackendUrl = String.fromEnvironment(
    'SIGNAL_BACKEND_URL',
    defaultValue: 'https://ai-trading-signals-api-production.up.railway.app',
  );

  static Uri get healthUri => Uri.parse(
        '${backendUrl.replaceAll(RegExp(r'/+$'), '')}/health',
      );
}
