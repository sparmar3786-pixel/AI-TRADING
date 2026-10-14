"""Internal SmartWebSocketV2 manager; tokens never leave this process."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable


EXCHANGE_TYPES = {"NSE": 1, "NFO": 2, "BSE": 3, "BFO": 4, "MCX": 5}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _price(value: Any) -> float | None:
    number = _num(value)
    # SmartWebSocketV2 transmits prices in paise (100x rupee price).
    return number / 100.0 if number is not None else None


def _depth(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        price = _price(row.get("price"))
        quantity = _num(row.get("quantity"))
        if price is not None and quantity is not None:
            result.append({"price": price, "quantity": quantity, "orders": _num(row.get("orders"))})
    return result


def _timestamp(value: Any) -> str | None:
    number = _num(value)
    if number is not None:
        try:
            seconds = number / 1000 if number > 10_000_000_000 else number
            return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
    return None


class AngelOneStream:
    """Owns one WebSocket client and caches normalized latest ticks by token."""

    def __init__(self, adapter: Any, on_tick: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._adapter = adapter
        self._on_tick_callback = on_tick
        self._lock = threading.RLock()
        self._client: Any = None
        self._thread: threading.Thread | None = None
        self._desired: dict[int, set[str]] = {}
        self._ticks: dict[str, dict[str, Any]] = {}
        self._started_at: float | None = None
        self._last_tick_at: float | None = None
        self._tick_count = 0
        self._open = False
        self._error: str | None = None
        self._closed_at: float | None = None

    def start(self, subscriptions: dict[int, list[str]] | None = None) -> dict[str, Any]:
        with self._lock:
            added: dict[int, list[str]] = {}
            for exchange_type, tokens in (subscriptions or {}).items():
                bucket = self._desired.setdefault(int(exchange_type), set())
                delta = sorted({str(t) for t in tokens if str(t)} - bucket)
                bucket.update(str(t) for t in tokens if str(t))
                if delta:
                    added[int(exchange_type)] = delta
            if self._client is not None and self._thread is not None and self._thread.is_alive():
                client = self._client
                opened = self._open
                for exchange_type, tokens in added.items():
                    if opened:
                        self._send_subscription(client, exchange_type, tokens)
                return self.status()
            credentials = self._adapter.websocket_credentials()
            try:
                from SmartApi.smartWebSocketV2 import SmartWebSocketV2
            except ImportError as exc:
                self._error = "SmartWebSocketV2 is unavailable in the installed SmartAPI SDK"
                raise RuntimeError(self._error) from exc
            self._client = SmartWebSocketV2(
                credentials["jwt_token"],
                credentials["api_key"],
                credentials["client_code"],
                credentials["feed_token"],
            )
            self._client.on_open = self._on_open
            self._client.on_data = self._on_data
            self._client.on_error = self._on_error
            self._client.on_close = self._on_close
            self._started_at = time.monotonic()
            self._closed_at = None
            self._open = False
            self._error = None
            self._thread = threading.Thread(target=self._connect, name="angelone-smartwebsocketv2", daemon=True)
            self._thread.start()
            return self.status()

    def _connect(self) -> None:
        try:
            self._client.connect()
        except Exception:
            # Do not log the exception string: SDK exceptions can contain request data.
            with self._lock:
                self._open = False
                self._error = "SmartWebSocketV2 connection failed; inspect broker/network status and reconnect."

    def _on_open(self, *_args: Any) -> None:
        with self._lock:
            self._open = True
            self._error = None
            client = self._client
            desired = {kind: sorted(tokens) for kind, tokens in self._desired.items() if tokens}
        for exchange_type, tokens in desired.items():
            self._send_subscription(client, exchange_type, tokens)

    def _send_subscription(self, client: Any, exchange_type: int, tokens: list[str]) -> None:
        if not client or not tokens:
            return
        # Mode 3 is SmartAPI's snap-quote mode; depth fields are used only when
        # the SDK actually supplies them in a tick.
        try:
            # Keep each subscription request within the conservative 50-token batch.
            for offset in range(0, len(tokens), 50):
                client.subscribe("ai-trading-live", 3, [{"exchangeType": int(exchange_type), "tokens": tokens[offset:offset + 50]}])
        except Exception:
            with self._lock:
                self._error = "SmartWebSocketV2 subscription failed for one or more market tokens."

    def subscribe(self, exchange_type: int, tokens: list[str]) -> None:
        clean = {str(token).strip() for token in tokens if str(token).strip()}
        with self._lock:
            previous = self._desired.setdefault(int(exchange_type), set())
            delta = sorted(clean - previous)
            previous.update(clean)
            client = self._client
            opened = self._open
        if opened and delta:
            self._send_subscription(client, int(exchange_type), delta)

    def _on_data(self, *args: Any) -> None:
        message = args[-1] if args else None
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8")
            except UnicodeDecodeError:
                return
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                return
        if not isinstance(message, dict):
            return
        token = str(message.get("token") or message.get("symbolToken") or "").strip()
        if not token:
            return
        buy = _depth(message.get("best_5_buy_data") or message.get("best5BuyData") or [])
        sell = _depth(message.get("best_5_sell_data") or message.get("best5SellData") or [])
        tick = {
            "symbolToken": token,
            "ltp": _price(message.get("last_traded_price") or message.get("ltp")),
            "exchFeedTime": _timestamp(message.get("exchange_timestamp") or message.get("exchangeTimestamp")),
            "tradeVolume": _num(message.get("volume_trade_for_the_day") or message.get("tradeVolume")),
            "opnInterest": _num(message.get("open_interest") or message.get("opnInterest")),
            "best5Data": {"buy": buy, "sell": sell},
            "_source_mode": "WEBSOCKET_V2",
        }
        with self._lock:
            self._ticks[token] = tick
            self._last_tick_at = time.monotonic()
            self._tick_count += 1
        callback = self._on_tick_callback
        if callback is not None:
            try:
                callback(dict(tick))
            except Exception:
                # Chart telemetry must never break the broker feed callback.
                pass

    def _on_error(self, *_args: Any) -> None:
        with self._lock:
            self._open = False
            self._error = "SmartWebSocketV2 reported a connection or subscription error."

    def _on_close(self, *_args: Any) -> None:
        with self._lock:
            self._open = False
            self._closed_at = time.monotonic()

    def get_tick(self, token: str, max_age_seconds: float = 60.0) -> dict[str, Any] | None:
        with self._lock:
            tick = self._ticks.get(str(token))
            if tick is None:
                return None
            stamp = tick.get("exchFeedTime")
            if not stamp:
                return None
            try:
                parsed = datetime.fromisoformat(stamp)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
            except ValueError:
                return None
            if age < 0 or age > max_age_seconds:
                return None
            return dict(tick)

    def stop(self) -> None:
        with self._lock:
            client = self._client
            self._open = False
            self._client = None
            self._thread = None
            self._started_at = None
        if client is not None:
            try:
                close = getattr(client, "close_connection", None) or getattr(client, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        with self._lock:
            last_age = time.monotonic() - self._last_tick_at if self._last_tick_at else None
            return {
                "stream_started": self._started_at is not None,
                "stream_open": self._open,
                "tick_count": self._tick_count,
                "unique_tokens_seen": len(self._ticks),
                "last_tick_age_seconds": round(last_age, 2) if last_age is not None else None,
                "last_tick_utc": self._ticks[next(reversed(self._ticks))].get("exchFeedTime") if self._ticks else None,
                "last_error": self._error,
                "subscribed_token_count": sum(len(tokens) for tokens in self._desired.values()),
                "mode": "WEBSOCKET_V2",
            }
