class AppConfig {
  // Existing AI/chat and general API backend remains separate to avoid breaking
  // cloud AI features while the dedicated signal API is deployed and validated.
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
