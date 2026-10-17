import 'dart:async';
import 'api.dart';

class LiveSignalFeed {
  LiveSignalFeed(this.api);
  final FreshApi api;
  final StreamController<Map<String, dynamic>> _controller =
      StreamController<Map<String, dynamic>>.broadcast();
  final StreamController<String> _errorsController =
      StreamController<String>.broadcast();
  Timer? _timer;
  String? _lastError;

  Stream<Map<String, dynamic>> get stream => _controller.stream;

  /// Refresh errors are observable separately from signal payloads so callers
  /// can distinguish "no signal" from a failed backend poll.
  Stream<String> get errors => _errorsController.stream;
  String? get lastError => _lastError;

  void start() {
    _timer ??= Timer.periodic(
      const Duration(seconds: 5),
      (_) async {
        try {
          final payload = await api.signals();
          _lastError = null;
          if (!_controller.isClosed) {
            _controller.add(payload);
          }
        } catch (error) {
          final message = 'Signal refresh failed: $error';
          _lastError = message;
          if (!_errorsController.isClosed) {
            _errorsController.add(message);
          }
        }
      },
    );
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> dispose() async {
    stop();
    await _controller.close();
    await _errorsController.close();
  }
}
