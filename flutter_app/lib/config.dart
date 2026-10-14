class AppConfig {
  // BACKEND_URL remains a legacy compatibility/health endpoint.
  // SIGNAL_BACKEND_URL owns AI providers, Angel One market data, signals,
  // paper ledger and read-only account routes for the AI-TRADING repository.
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
