"""Bounded, fail-closed Angel One tick-stream supervisor.

Inject an SDK-specific connector and parser: SmartAPI WebSocket V2 uses an
SDK-specific authenticated connection and binary tick packet format. This
module deliberately does not guess headers or decode arbitrary packets as LTP.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class Tick:
    token: str
    ltp: float
    received_at: float


class AngelWebSocketSupervisor:
    def __init__(self, connector_factory: Callable[[Callable[[Any], None], Callable[[Exception], None]], Any],
                 parser: Callable[[Any], Optional[tuple[str, float]]],
                 on_tick: Optional[Callable[[Tick], None]] = None,
                 reconnect_seconds: float = 5.0, max_reconnects: int = 20,
                 max_tick_age_seconds: float = 5.0):
        if reconnect_seconds <= 0 or max_reconnects < 1 or max_tick_age_seconds <= 0:
            raise ValueError("reconnect and freshness settings must be positive")
        self.connector_factory, self.parser, self.on_tick = connector_factory, parser, on_tick
        self.reconnect_seconds, self.max_reconnects = reconnect_seconds, max_reconnects
        self.max_tick_age_seconds = max_tick_age_seconds
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._connection: Any = None
        self._latest: dict[str, Tick] = {}
        self.connected = False
        self.last_error: Optional[str] = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="angel-ws-supervisor", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._lock:
            connection = self._connection
        if connection is not None:
            try:
                close = getattr(connection, "close", None)
                if callable(close): close()
            except Exception as exc:
                self.last_error = type(exc).__name__
        thread = self._thread
        if thread and thread is not threading.current_thread(): thread.join(timeout)
        self.connected = False

    def latest(self, token: str, now: Optional[float] = None) -> Optional[Tick]:
        now = time.time() if now is None else now
        with self._lock:
            tick = self._latest.get(str(token))
        if tick is None or now < tick.received_at or now - tick.received_at > self.max_tick_age_seconds:
            return None
        return tick

    def _on_message(self, message: Any) -> None:
        try:
            parsed = self.parser(message)
            if parsed is None: return
            token, ltp = str(parsed[0]), float(parsed[1])
            if not token or not (ltp > 0) or ltp != ltp or ltp in (float("inf"), float("-inf")):
                return
            tick = Tick(token, ltp, time.time())
            with self._lock: self._latest[token] = tick
            if self.on_tick: self.on_tick(tick)
        except Exception as exc:
            self.last_error = f"tick_parse:{type(exc).__name__}"

    def _run(self) -> None:
        attempts = 0
        while not self._stop.is_set() and attempts < self.max_reconnects:
            try:
                connection = self.connector_factory(self._on_message, self._on_error)
                with self._lock: self._connection = connection
                self.connected = True
                run_forever = getattr(connection, "connect", None) or getattr(connection, "run_forever", None)
                if not callable(run_forever): raise TypeError("connector must expose connect() or run_forever()")
                run_forever()
                if not self._stop.is_set(): raise ConnectionError("websocket ended unexpectedly")
            except Exception as exc:
                self.connected = False
                self.last_error = f"connection:{type(exc).__name__}"
                attempts += 1
                if not self._stop.wait(self.reconnect_seconds): continue
            finally:
                with self._lock: self._connection = None
                self.connected = False

    def _on_error(self, error: Exception) -> None:
        self.last_error = f"websocket:{type(error).__name__}"
