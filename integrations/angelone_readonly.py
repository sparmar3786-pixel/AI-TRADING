"""Read-only Angel One SmartAPI adapter.

Credentials and generated JWT/refresh/feed tokens stay in server memory. This
adapter deliberately exposes market-data/profile calls only: it has no order
placement, modification, or cancellation methods.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any


class AngelOneConfigError(RuntimeError):
    """Raised when required server-side credentials are missing."""


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise AngelOneConfigError(f"Missing required environment variable: {name}")
    return value


def _ok(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("status") is not True:
        code = response.get("errorcode", "unknown") if isinstance(response, dict) else "invalid_response"
        message = response.get("message", "SmartAPI request failed") if isinstance(response, dict) else "Invalid SmartAPI response"
        raise RuntimeError(f"Angel One SmartAPI error ({code}): {message}")
    return response


class AngelOneReadOnly:
    """Lazy-login wrapper around the official smartapi-python SDK.

    SmartAPI SDK versions differ in the object returned by generateSession:
    some return login tokens, while current versions can return the profile.
    Read tokens from the SDK's in-memory properties first and never assume the
    return payload itself contains refreshToken.
    """

    ALLOWED_EXCHANGES = {"NSE", "BSE", "NFO", "BFO", "MCX", "NCX", "CDS"}
    ALLOWED_INTERVALS = {
        "ONE_MINUTE", "THREE_MINUTE", "FIVE_MINUTE", "TEN_MINUTE",
        "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR", "ONE_DAY",
    }
    SESSION_RELOGIN_SECONDS = 18 * 60 * 60

    def __init__(self) -> None:
        self._client = None
        self._refresh_token: str | None = None
        self._logged_in_at: float | None = None
        self._lock = threading.RLock()

    def _login(self):
        with self._lock:
            if (
                self._client is not None
                and self._refresh_token
                and self._logged_in_at is not None
                and time.monotonic() - self._logged_in_at < self.SESSION_RELOGIN_SECONDS
            ):
                return self._client

            api_key = _required_env("ANGEL_API_KEY")
            client_code = _required_env("ANGEL_CLIENT_CODE")
            pin = _required_env("ANGEL_PIN")
            totp_secret = _required_env("ANGEL_TOTP_SECRET")
            try:
                import pyotp
                from SmartApi import SmartConnect
            except ImportError as exc:
                raise RuntimeError(
                    "Install the optional Angel One dependencies: smartapi-python and pyotp"
                ) from exc

            client = SmartConnect(api_key=api_key)
            response = _ok(client.generateSession(client_code, pin, pyotp.TOTP(totp_secret).now()))
            data = response.get("data") or {}
            # SDK generateSession may return a profile object after it has
            # already populated these token properties.
            refresh_token = (
                getattr(client, "refresh_token", None)
                or getattr(client, "_refresh_token", None)
                or data.get("refreshToken")
            )
            if not refresh_token:
                raise RuntimeError(
                    "Angel One login returned no refresh token in SDK state or response; "
                    "check the installed SmartAPI SDK version."
                )
            self._client = client
            self._refresh_token = str(refresh_token)
            self._logged_in_at = time.monotonic()
            return client

    def profile(self) -> dict[str, Any]:
        """Return a minimal authenticated profile; no credentials or tokens."""
        client = self._login()
        response = _ok(client.getProfile(self._refresh_token))
        data = response.get("data") or {}
        return {
            "client_code": data.get("clientcode"),
            "name": data.get("name"),
            "source": "angelone_smartapi",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    def ltp(self, exchange: str, tradingsymbol: str, symboltoken: str) -> dict[str, Any]:
        """Fetch LTP for a known SmartAPI contract."""
        exchange = exchange.strip().upper()
        if exchange not in self.ALLOWED_EXCHANGES:
            raise ValueError(f"Unsupported exchange {exchange!r}; use one of {sorted(self.ALLOWED_EXCHANGES)}")
        if not tradingsymbol.strip() or not symboltoken.strip():
            raise ValueError("tradingsymbol and symboltoken are required")
        client = self._login()
        response = _ok(client.ltpData(exchange, tradingsymbol, symboltoken))
        data = response.get("data") or {}
        return {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "symboltoken": symboltoken,
            "ltp": data.get("ltp"),
            "source": "angelone_smartapi",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source_timestamp": data.get("exchange_timestamp") or data.get("exch_feed_time"),
            "freshness_note": "observed_at is server fetch time; source timestamp may be unavailable",
        }

    def market_data(self, mode: str, exchange_tokens: dict[str, list[str]]) -> dict[str, Any]:
        """Fetch SmartAPI market quotes (FULL includes top-five depth when available)."""
        normalized_mode = mode.strip().upper()
        if normalized_mode not in {"LTP", "OHLC", "FULL"}:
            raise ValueError("mode must be LTP, OHLC, or FULL")
        if not isinstance(exchange_tokens, dict) or not exchange_tokens:
            raise ValueError("exchange_tokens must be a non-empty exchange-to-token mapping")
        normalized: dict[str, list[str]] = {}
        total = 0
        for raw_exchange, raw_tokens in exchange_tokens.items():
            exchange = str(raw_exchange).strip().upper()
            if exchange not in self.ALLOWED_EXCHANGES:
                raise ValueError(f"Unsupported exchange {exchange!r}")
            if not isinstance(raw_tokens, list):
                raise ValueError(f"Tokens for {exchange} must be a list")
            tokens = list(dict.fromkeys(str(token).strip() for token in raw_tokens if str(token).strip()))
            if not tokens:
                continue
            if len(tokens) > 50:
                raise ValueError(f"At most 50 tokens per exchange are allowed per market-data request ({exchange})")
            normalized[exchange] = tokens
            total += len(tokens)
        if not normalized or total > 100:
            raise ValueError("Provide 1-100 tokens total, with at most 50 per exchange")
        response = _ok(self._login().getMarketData(normalized_mode, normalized))
        return {
            "source": "angelone_smartapi",
            "mode": normalized_mode,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "data": response.get("data") or {},
        }

    def candles(
        self, exchange: str, symboltoken: str, interval: str,
        fromdate: str, todate: str,
    ) -> dict[str, Any]:
        """Fetch historical OHLCV bars. Caller must still validate exchange timestamps."""
        exchange = exchange.strip().upper()
        interval = interval.strip().upper()
        if exchange not in self.ALLOWED_EXCHANGES:
            raise ValueError(f"Unsupported exchange {exchange!r}")
        if interval not in self.ALLOWED_INTERVALS:
            raise ValueError(f"Unsupported interval {interval!r}")
        if not symboltoken.strip() or not fromdate.strip() or not todate.strip():
            raise ValueError("symboltoken, fromdate, and todate are required")
        try:
            start = datetime.strptime(fromdate, "%Y-%m-%d %H:%M")
            end = datetime.strptime(todate, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise ValueError("fromdate/todate must use YYYY-MM-DD HH:MM") from exc
        if start >= end:
            raise ValueError("fromdate must be before todate")
        params = {
            "exchange": exchange, "symboltoken": symboltoken,
            "interval": interval, "fromdate": fromdate, "todate": todate,
        }
        response = _ok(self._login().getCandleData(params))
        return {
            "source": "angelone_smartapi",
            "exchange": exchange,
            "symboltoken": symboltoken,
            "interval": interval,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "candles": response.get("data") or [],
        }

    def option_greeks(self, name: str, expirydate: str) -> dict[str, Any]:
        """Fetch NSE option Greeks for an underlying/expiry (not an order API)."""
        if not name.strip() or not expirydate.strip():
            raise ValueError("name and expirydate are required")
        if len(name) > 40 or len(expirydate) > 20:
            raise ValueError("name or expirydate is too long")
        response = _ok(self._login().optionGreek({"name": name.strip().upper(), "expirydate": expirydate.strip().upper()}))
        return {
            "source": "angelone_smartapi",
            "name": name.strip().upper(),
            "expirydate": expirydate.strip().upper(),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "data": response.get("data") or [],
        }
