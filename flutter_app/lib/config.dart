class AppConfig {
  // BACKEND_URL preserves the existing AI/chat service in release builds.
  // SIGNAL_BACKEND_URL owns Angel One market data, signals, paper ledger and
  // read-only account routes. They are intentionally separate in the APK.
  static const String backendUrl = String.fromEnvironment(
    'BACKEND_URL',
    defaultValue: 'https://nse-algo-backend-final-production.up.railway.app',
  );

  static const String signalBackendUrl = String.fromEnvironment(
    'SIGNAL_BACKEND_URL',
    defaultValue: 'https://ai-trading-signals-api-production.up.railway.app',
  );

  static Uri get healthUri => Uri.parse(
        '${backendUrl.replaceAll(RegExp(r'/+$'), '')}/health',
      );
}
