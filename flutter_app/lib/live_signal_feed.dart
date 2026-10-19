import 'dart:async';
import 'api.dart';

class LiveSignalFeed {
  LiveSignalFeed(this.api);
  final FreshApi api;
  final StreamController<Map<String, dynamic>> _controller =
      StreamController<Map<String, dynamic>>.broadcast();
  Timer? _timer;

  Stream<Map<String, dynamic>> get stream => _controller.stream;

  void start() {
    _timer ??= Timer.periodic(
      const Duration(seconds: 15),
      (_) async {
        try {
          final payload = await api.signals();
          if (!_controller.isClosed) {
            _controller.add(payload);
          }
        } catch (error, stackTrace) {
          // Do not silently swallow transport/authentication errors; listeners
          // can render a data-error state while keeping signals fail-closed.
          if (!_controller.isClosed) _controller.addError(error, stackTrace);
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
  }
}
