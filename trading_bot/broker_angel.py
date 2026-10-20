from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Any

class AngelReadOnlyBroker:
    """Read-only SmartAPI adapter. Deliberately has no place_order method."""
    def __init__(self, api_key: str, client_code: str, pin: str, totp_secret: str):
        self.api_key = api_key; self.client_code = client_code; self.pin = pin; self.totp_secret = totp_secret
        self.smart = None

    @classmethod
    def from_env(cls):
        keys = {'ANGEL_API_KEY': os.getenv('ANGEL_API_KEY'), 'ANGEL_CLIENT_CODE': os.getenv('ANGEL_CLIENT_CODE'),
                'ANGEL_PIN': os.getenv('ANGEL_PIN'), 'ANGEL_TOTP_SECRET': os.getenv('ANGEL_TOTP_SECRET')}
        missing = [key for key, value in keys.items() if not value]
        if missing:
            raise RuntimeError('Missing backend environment variables: ' + ', '.join(missing))
        return cls(keys['ANGEL_API_KEY'], keys['ANGEL_CLIENT_CODE'], keys['ANGEL_PIN'], keys['ANGEL_TOTP_SECRET'])

    def login(self) -> None:
        if self.smart is not None:
            return
        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as exc:
            raise RuntimeError('Install smartapi-python and pyotp in the backend environment') from exc
        smart = SmartConnect(api_key=self.api_key)
        result = smart.generateSession(self.client_code, self.pin, pyotp.TOTP(self.totp_secret).now())
        if not isinstance(result, dict) or result.get('status') is not True or not isinstance(result.get('data'), dict):
            raise RuntimeError('Angel One login failed; session was not established')
        self.smart = smart

    def fetch_candles(self, exchange: str, symbol_token: str, interval: str = 'FIVE_MINUTE', lookback_days: int = 3) -> list[dict[str, Any]]:
        if not symbol_token or not symbol_token.isdigit():
            raise ValueError('A valid numeric Angel One symbol token is required')
        self.login()
        now = datetime.now()
        start = now - timedelta(days=max(1, min(int(lookback_days), 30)))
        response = self.smart.getCandleData({'exchange': exchange, 'symboltoken': symbol_token,
            'interval': interval, 'fromdate': start.strftime('%Y-%m-%d %H:%M'), 'todate': now.strftime('%Y-%m-%d %H:%M')})
        rows = response.get('data') if isinstance(response, dict) and response.get('status') is True else None
        if not isinstance(rows, list) or not rows:
            raise RuntimeError('Angel One returned no candle data')
        output = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            try:
                output.append({'ts': str(row[0]), 'open': float(row[1]), 'high': float(row[2]),
                    'low': float(row[3]), 'close': float(row[4]), 'volume': float(row[5])})
            except (TypeError, ValueError):
                continue
        if not output:
            raise RuntimeError('Angel One candle payload did not contain valid OHLCV rows')
        return output

    def fetch_ltp(self, exchange: str, trading_symbol: str, symbol_token: str) -> float:
        if not trading_symbol or not symbol_token:
            raise ValueError('Trading symbol and symbol token are required')
        self.login()
        response = self.smart.getLtpData(exchange, trading_symbol, symbol_token)
        data = response.get('data') if isinstance(response, dict) and response.get('status') is True else None
        ltp = data.get('ltp') if isinstance(data, dict) else None
        value = float(ltp) if ltp is not None else 0.0
        if value <= 0:
            raise RuntimeError('Angel One returned no valid LTP')
        return value
