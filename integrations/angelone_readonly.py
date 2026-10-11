"""Read-only Angel One SmartAPI adapter.

This module deliberately exposes profile and LTP reads only. It never places,
modifies, or cancels orders. Credentials must be supplied through server-side
environment variables; never bundle them in an APK or commit them to Git.
"""
from __future__ import annotations

import os
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
        # Avoid returning response bodies that might contain sensitive data.
        code = response.get("errorcode", "unknown") if isinstance(response, dict) else "invalid_response"
        message = response.get("message", "SmartAPI request failed") if isinstance(response, dict) else "Invalid SmartAPI response"
        raise RuntimeError(f"Angel One SmartAPI error ({code}): {message}")
    return response


class AngelOneReadOnly:
    """Small lazy-login wrapper around the official smartapi-python SDK."""

    def __init__(self) -> None:
        self._client = None
        self._refresh_token: str | None = None

    def _login(self):
        if self._client is not None:
            return self._client
        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional Angel One dependencies: smartapi-python and pyotp"
            ) from exc

        api_key = _required_env("ANGEL_API_KEY")
        client_code = _required_env("ANGEL_CLIENT_CODE")
        pin = _required_env("ANGEL_PIN")
        totp_secret = _required_env("ANGEL_TOTP_SECRET")
        client = SmartConnect(api_key=api_key)
        session = _ok(client.generateSession(client_code, pin, pyotp.TOTP(totp_secret).now()))
        data = session.get("data") or {}
        refresh_token = data.get("refreshToken")
        if not refresh_token:
            raise RuntimeError("Angel One login response did not include refreshToken")
        self._client = client
        self._refresh_token = refresh_token
        return client

    def profile(self) -> dict[str, Any]:
        """Return a minimal authenticated profile; no credentials are returned."""
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
        """Fetch LTP for a known SmartAPI contract; does not infer a market timestamp."""
        allowed = {"NSE", "BSE", "NFO", "BFO", "MCX"}
        exchange = exchange.strip().upper()
        if exchange not in allowed:
            raise ValueError(f"Unsupported exchange {exchange!r}; use one of {sorted(allowed)}")
        if not tradingsymbol.strip() or not symboltoken.strip():
            raise ValueError("tradingsymbol and symboltoken are required")
        client = self._login()
        response = _ok(client.ltpData(exchange, tradingsymbol, symboltoken))
        data = response.get("data") or {}
        # SmartAPI LTP payloads may not contain an exchange timestamp. Do not
        # label fetch time as exchange time or claim that the quote is real-time.
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
