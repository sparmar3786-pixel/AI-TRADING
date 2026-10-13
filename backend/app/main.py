"""AI-TRADING read-only live market API.

Signals fail closed: absent credentials, stale source timestamps, incomplete
option depth/Greeks, conflicting timeframes, or missing option ATR means WAIT.
This service never places, modifies, or cancels broker orders.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.request
import asyncio
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.angelone_readonly import AngelOneConfigError, AngelOneReadOnly
from integrations.angelone_stream import AngelOneStream, EXCHANGE_TYPES
from integrations.news_sentiment import cached_market_news_sentiment, fetch_market_news_sentiment
from quant_engine import evaluate_five_layer_signal, evaluate_futures_signal

from strategies.technical import atr as technical_atr, ema as technical_ema, rsi as technical_rsi, rsi_reversion, sma as technical_sma
from strategies.advanced import bollinger_bands, macd as advanced_macd, donchian_channels
from risk.position_sizing import position_size

app = FastAPI(title="AI-TRADING Read-only Signals API", version="1.0.0")
logger = logging.getLogger("ai_trading.angel")
# SmartAPI/logzero SDK error logs can include full request headers (API key/JWT)
# and payloads. Silence SDK transport logs before the first broker call; only
# sanitized application diagnostics below may reach Railway.
for _sdk_logger_name in (
    "SmartApi", "SmartApi.smartConnect", "urllib3", "requests",
    "logzero", "logzero_default",
):
    _sdk_logger = logging.getLogger(_sdk_logger_name)
    _sdk_logger.setLevel(logging.CRITICAL)
    _sdk_logger.propagate = False
try:
    # smartapi-python commonly logs through logzero.logger rather than the
    # stdlib logger named SmartApi, so suppress that logger and its handlers too.
    from logzero import logger as _smartapi_logzero_logger
    _smartapi_logzero_logger.setLevel(logging.CRITICAL)
    for _sdk_handler in _smartapi_logzero_logger.handlers:
        _sdk_handler.setLevel(logging.CRITICAL)
except Exception:
    pass
IST = ZoneInfo("Asia/Kolkata")
MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
MASTER_TTL_SECONDS = 6 * 60 * 60
SIGNAL_CACHE_SECONDS = 30
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
INDEXES: dict[str, dict[str, str]] = {
    "NIFTY": {"exchange": "NSE", "token": "99926000", "name": "NIFTY"},
    "BANKNIFTY": {"exchange": "NSE", "token": "99926009", "name": "BANKNIFTY"},
    "FINNIFTY": {"exchange": "NSE", "token": "99926037", "name": "FINNIFTY"},
    "MIDCPNIFTY": {"exchange": "NSE", "token": "99926074", "name": "MIDCPNIFTY"},
    "SENSEX": {"exchange": "BSE", "token": "99919000", "name": "SENSEX"},
    "BANKEX": {"exchange": "BSE", "token": "99919012", "name": "BANKEX"},
}
COMMODITY_NAMES = ("GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER")
_lock = threading.RLock()
_adapter: AngelOneReadOnly | None = None
_stream: AngelOneStream | None = None
_stream_adapter: AngelOneReadOnly | None = None
_stream_start_error: str | None = None
_news_refreshing: set[str] = set()
_news_lock = threading.Lock()
_saved_meta: dict[str, Any] = {}
_master_rows: list[dict[str, Any]] = []
_master_loaded_at = 0.0
_signal_cache: dict[str, Any] | None = None
_signal_cache_at = 0.0
_confirmation_states: dict[str, dict[str, Any]] = {}
_last_market: dict[str, Any] = {}
_option_history: dict[str, dict[str, float]] = {}


class ConnectRequest(BaseModel):
    angel_api_key: str | None = Field(default=None, max_length=256)
    angel_client_code: str | None = Field(default=None, max_length=128)
    angel_pin: str | None = Field(default=None, max_length=128)
    angel_totp: str | None = Field(default=None, max_length=128)
    remember_credentials: bool = True


class ResearchIndicatorsRequest(BaseModel):
    """Caller-supplied OHLCV candles; this endpoint does not claim they are live."""
    candles: list[list[Any]] = Field(min_length=30, max_length=500)
    ema_fast: int = Field(default=8, ge=2, le=50)
    ema_slow: int = Field(default=21, ge=3, le=100)
    rsi_period: int = Field(default=14, ge=2, le=50)
    atr_period: int = Field(default=14, ge=2, le=50)
    band_period: int = Field(default=20, ge=2, le=100)
    channel_period: int = Field(default=20, ge=2, le=100)


class BacktestRequest(BaseModel):
    index: str = "NIFTY"
    exchange: str | None = None
    symboltoken: str | None = Field(default=None, min_length=1, max_length=32)
    interval: str = "FIVE_MINUTE"
    from_date: str | None = None
    to_date: str | None = None
    fromdate: str | None = None
    todate: str | None = None
    fast_ema: int = Field(default=8, ge=2, le=100)
    slow_ema: int = Field(default=13, ge=3, le=200)
    atr_period: int = Field(default=14, ge=2, le=100)
    stop_atr: float = Field(default=1.5, gt=0, le=10)
    target_r: float = Field(default=2.0, gt=0, le=20)
    max_hold_bars: int = Field(default=30, ge=1, le=500)
    slippage_r: float = Field(default=0.02, ge=0, le=1)
    transaction_cost_r: float = Field(default=0.02, ge=0, le=1)
    initial_capital: float = Field(default=100000.0, gt=0, le=1000000000)


def _device(x_device_id: str = Header(default="")) -> str:
    # This is a device-scope identifier, not a substitute for account auth.
    if not DEVICE_ID_RE.fullmatch(x_device_id or ""):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Device-Id")
    return x_device_id


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            # SmartAPI timestamps are sometimes epoch milliseconds.
            stamp = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(stamp, timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=IST)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _encryption_key() -> bytes:
    raw = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise HTTPException(
            status_code=503,
            detail="Remember credentials requires CREDENTIALS_ENCRYPTION_KEY (32 random bytes, base64) in Railway variables.",
        )
    try:
        key = bytes.fromhex(raw) if re.fullmatch(r"[0-9a-fA-F]{64}", raw) else base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (ValueError, base64.binascii.Error) as exc:
        raise HTTPException(status_code=503, detail="CREDENTIALS_ENCRYPTION_KEY must be 32 bytes encoded as base64 or 64 hex characters.") from exc
    if len(key) != 32:
        raise HTTPException(status_code=503, detail="CREDENTIALS_ENCRYPTION_KEY must decode to exactly 32 bytes.")
    return key


def _refresh_news_worker(index: str) -> None:
    try:
        fetch_market_news_sentiment(index)
    except Exception:
        pass
    finally:
        with _news_lock:
            _news_refreshing.discard(index)


def _schedule_news_refresh(indexes: list[str]) -> None:
    if not (os.getenv("EXA_API_KEY", "").strip() or os.getenv("TAVILY_API_KEY", "").strip()):
        return
    for index in indexes:
        key = index.strip().upper()
        with _news_lock:
            if key in _news_refreshing:
                continue
            _news_refreshing.add(key)
        threading.Thread(target=_refresh_news_worker, args=(key,), name=f"news-{key.lower()}", daemon=True).start()


def _credential_path() -> Path:
    return Path(os.getenv("ANGEL_CREDENTIALS_FILE", "/data/angel_credentials.enc"))


def _save_credentials(credentials: dict[str, str]) -> None:
    # TOTP is intentionally excluded; a fresh TOTP is required after session expiry.
    payload = json.dumps({
        "version": 1,
        "angel_api_key": credentials["angel_api_key"],
        "angel_client_code": credentials["angel_client_code"],
        "angel_pin": credentials["angel_pin"],
    }, separators=(",", ":")).encode()
    nonce = os.urandom(12)
    ciphertext = AESGCM(_encryption_key()).encrypt(nonce, payload, b"AI-TRADING-ANGEL-CREDENTIALS-v1")
    path = _credential_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(base64.urlsafe_b64encode(nonce + ciphertext))
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not persist encrypted credentials. Attach a Railway persistent volume at /data or disable Remember credentials.",
        ) from exc


def _load_credentials() -> dict[str, str]:
    path = _credential_path()
    if not path.is_file():
        return {}
    try:
        raw = base64.urlsafe_b64decode(path.read_bytes())
        plaintext = AESGCM(_encryption_key()).decrypt(raw[:12], raw[12:], b"AI-TRADING-ANGEL-CREDENTIALS-v1")
        value = json.loads(plaintext)
        return {key: str(value[key]) for key in ("angel_api_key", "angel_client_code", "angel_pin") if value.get(key)}
    except Exception:
        # Do not log ciphertext, plaintext or exception payloads.
        return {}

def _forget_credentials() -> None:
    path = _credential_path()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Could not remove saved encrypted credentials from the persistent volume.") from exc


def _credentials_from_env() -> dict[str, str]:
    mapping = {
        "angel_api_key": "ANGEL_API_KEY",
        "angel_client_code": "ANGEL_CLIENT_CODE",
        "angel_pin": "ANGEL_PIN",
        "angel_totp_secret": "ANGEL_TOTP_SECRET",
    }
    return {key: os.getenv(env, "").strip() for key, env in mapping.items() if os.getenv(env, "").strip()}


def _current_adapter(attempt_env_login: bool = False) -> AngelOneReadOnly | None:
    global _adapter
    with _lock:
        if _adapter is None and attempt_env_login:
            creds = _credentials_from_env()
            if len(creds) == 4:
                _adapter = AngelOneReadOnly(creds)
                try:
                    _adapter.profile()
                    try:
                        _start_stream(_adapter)
                    except Exception:
                        pass  # REST fallback remains available if WebSocket setup fails.
                except Exception:
                    _adapter = None
        return _adapter


def _require_adapter() -> AngelOneReadOnly:
    adapter = _current_adapter(attempt_env_login=True)
    if adapter is None:
        raise HTTPException(status_code=503, detail="Angel One is not connected. Open API & Railway and connect with API key, Client ID, MPIN and current TOTP.")
    try:
        adapter.profile()
        try:
            _start_stream(adapter)
        except Exception:
            pass  # Never fail a valid REST session solely because WebSocket is unavailable.
    except AngelOneConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Angel One session is unavailable or expired. Reconnect with a fresh TOTP.") from exc
    return adapter


def _load_master(force: bool = False) -> list[dict[str, Any]]:
    global _master_rows, _master_loaded_at
    with _lock:
        if _master_rows and not force and time.monotonic() - _master_loaded_at < MASTER_TTL_SECONDS:
            return _master_rows
    request = urllib.request.Request(MASTER_URL, headers={"User-Agent": "AI-TRADING/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            rows = json.loads(response.read().decode("utf-8"))
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty instrument master")
        normalized = [row for row in rows if isinstance(row, dict)]
    except Exception as exc:
        with _lock:
            if _master_rows and not force:
                return _master_rows
        raise HTTPException(status_code=502, detail="Angel One instrument master download failed; live contract selection is unavailable.") from exc
    with _lock:
        _master_rows = normalized
        _master_loaded_at = time.monotonic()
        return _master_rows


def _start_stream(adapter: AngelOneReadOnly, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    global _stream, _stream_adapter, _stream_start_error
    subscriptions: dict[int, list[str]] = {}
    for config in INDEXES.values():
        exchange_type = EXCHANGE_TYPES.get(config["exchange"])
        if exchange_type:
            subscriptions.setdefault(exchange_type, []).append(config["token"])
    if rows:
        today = datetime.now(IST).date()
        for name in COMMODITY_NAMES:
            contracts = [
                row for row in rows
                if str(row.get("exch_seg", "")).upper() == "MCX"
                and str(row.get("name", "")).upper() == name
                and str(row.get("instrumenttype", "")).upper() == "FUTCOM"
                and row.get("token")
                and _expiry_date(row.get("expiry")) is not None
                and _expiry_date(row.get("expiry")) >= today
            ]
            contracts.sort(key=lambda row: _expiry_date(row.get("expiry")) or date.max)
            if contracts:
                subscriptions.setdefault(EXCHANGE_TYPES["MCX"], []).append(str(contracts[0]["token"]))
    with _lock:
        if _stream is None or _stream_adapter is not adapter:
            if _stream is not None:
                _stream.stop()
            _stream = AngelOneStream(adapter)
            _stream_adapter = adapter
        try:
            status = _stream.start(subscriptions)
            _stream_start_error = None
            return status
        except Exception:
            _stream_start_error = "SmartWebSocketV2 could not start; timestamp-validated REST fallback remains enabled."
            return _stream.status()


def _find_index_contract(rows: list[dict[str, Any]], index: str) -> dict[str, str]:
    config = INDEXES[index]
    token = config["token"]
    for row in rows:
        if str(row.get("token", "")) == token:
            exchange = str(row.get("exch_seg", config["exchange"])).upper()
            return {"exchange": exchange, "token": token, "symbol": str(row.get("symbol", config["name"])), "name": config["name"]}
    return {**config, "symbol": config["name"]}


def _quote_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data") or {}
    fetched = data.get("fetched") if isinstance(data, dict) else None
    return fetched if isinstance(fetched, list) else []


def _book(quote: dict[str, Any]) -> tuple[float | None, float | None, float, float]:
    raw = quote.get("best5Data") or quote.get("depth") or {}
    if isinstance(raw, list):
        buy = [x for x in raw if isinstance(x, dict) and str(x.get("side", "")).lower() in ("buy", "b")]
        sell = [x for x in raw if isinstance(x, dict) and str(x.get("side", "")).lower() in ("sell", "s")]
    elif isinstance(raw, dict):
        buy = raw.get("buy") or raw.get("bids") or []
        sell = raw.get("sell") or raw.get("asks") or []
    else:
        buy, sell = [], []
    buy = [x for x in buy if isinstance(x, dict)]
    sell = [x for x in sell if isinstance(x, dict)]
    bid = _number(buy[0].get("price")) if buy else None
    ask = _number(sell[0].get("price")) if sell else None
    buy_volume = sum(_number(x.get("quantity")) or 0 for x in buy)
    sell_volume = sum(_number(x.get("quantity")) or 0 for x in sell)
    return bid, ask, buy_volume, sell_volume


def _quote_timestamp(quote: dict[str, Any]) -> str | None:
    for key in ("exchFeedTime", "exchTradeTime", "exchange_timestamp", "exch_feed_time", "timestamp"):
        value = _iso(quote.get(key))
        if value:
            return value
    return None


def _quotes(adapter: AngelOneReadOnly, exchange: str, tokens: list[str]) -> dict[str, dict[str, Any]]:
    if not tokens:
        return {}
    unique_tokens = list(dict.fromkeys(str(token) for token in tokens if str(token)))
    output: dict[str, dict[str, Any]] = {}
    exchange_type = EXCHANGE_TYPES.get(exchange.upper())
    if _stream is not None and exchange_type is not None:
        _stream.subscribe(exchange_type, unique_tokens)
        for token in unique_tokens:
            tick = _stream.get_tick(token, max_age_seconds=60.0)
            if not tick or _number(tick.get("ltp")) is None:
                continue
            bid, ask, _, _ = _book(tick)
            # Quote/option gates require a real bid and ask. If this tick mode
            # omitted depth, request REST FULL depth instead of inventing it.
            if bid is not None and ask is not None:
                output[token] = tick
    missing = [token for token in unique_tokens if token not in output]
    if missing:
        try:
            result = adapter.market_data("FULL", {exchange: missing})
            for row in _quote_rows(result):
                token = str(row.get("symbolToken") or row.get("symboltoken") or row.get("token") or "")
                if token:
                    row["_source_mode"] = "REST_FULL_DEPTH"
                    output[token] = row
        except Exception:
            if not output:
                raise
    return output


def _strike_value(value: Any, underlying: float) -> float | None:
    strike = _number(value)
    if strike is None:
        return None
    # Angel One instrument master stores option strike in paise-like x100 units.
    if strike > underlying * 10:
        strike /= 100.0
    return strike


def _expiry_date(value: Any) -> date | None:
    text = str(value or "").strip().upper()
    for fmt in ("%d%b%Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _option_type(row: dict[str, Any]) -> str | None:
    raw = str(row.get("symbol", "")).upper()
    kind = str(row.get("instrumenttype", "")).upper()
    if kind not in ("OPTIDX", "OPTSTK", "OPTFUT"):
        return None
    if raw.endswith("CE") or raw.endswith("CALL"):
        return "CALL"
    if raw.endswith("PE") or raw.endswith("PUT"):
        return "PUT"
    return None


def _candle_closes(rows: list[Any]) -> list[float]:
    result = []
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            value = _number(row[4])
            if value is not None and value > 0:
                result.append(value)
    return result


def _resample_closes(closes: list[float], group_size: int) -> list[float]:
    if group_size <= 1:
        return closes[-80:]
    grouped = [closes[i + group_size - 1] for i in range(0, len(closes) - group_size + 1, group_size)]
    return grouped[-80:]


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    output = [values[0]]
    for value in values[1:]:
        output.append(alpha * value + (1.0 - alpha) * output[-1])
    return output


def _indicator_snapshot(closes: list[float], candle_rows: list[Any], today_rows: list[Any]) -> dict[str, Any]:
    if len(closes) < 30:
        return {}
    fast_line = technical_ema(closes, 8)
    slow_line = technical_ema(closes, 21)
    rsi_values = technical_rsi(closes, 14)
    rsi = float(rsi_values[-1]) if rsi_values and rsi_values[-1] is not None else 50.0
    ema12, ema26 = _ema_series(closes, 12), _ema_series(closes, 26)
    macd_line = [fast - slow for fast, slow in zip(ema12, ema26)]
    macd_signal = _ema_series(macd_line, 9)
    macd_histogram = macd_line[-1] - macd_signal[-1] if macd_line and macd_signal else None
    vwap_numerator = 0.0
    vwap_denominator = 0.0
    for row in today_rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        high, low, close, volume = _number(row[2]), _number(row[3]), _number(row[4]), _number(row[5])
        if high is None or low is None or close is None or volume is None or volume <= 0:
            continue
        vwap_numerator += ((high + low + close) / 3.0) * volume
        vwap_denominator += volume
    valid_indicator_rows = [
        row for row in candle_rows
        if isinstance(row, (list, tuple)) and len(row) >= 5
        and _number(row[2]) is not None and _number(row[3]) is not None and _number(row[4]) is not None
    ]
    indicator_highs = [float(row[2]) for row in valid_indicator_rows]
    indicator_lows = [float(row[3]) for row in valid_indicator_rows]
    indicator_closes = [float(row[4]) for row in valid_indicator_rows]
    atr_values = technical_atr(indicator_highs, indicator_lows, indicator_closes, 14) if len(indicator_closes) >= 14 else []
    sma20_values = technical_sma(closes, 20)
    sma50_values = technical_sma(closes, 50)
    ema50_values = technical_ema(closes, 50)
    ema200_values = technical_ema(closes, 200)
    reversion_values = rsi_reversion(closes, 14)
    sma20 = sma20_values[-1] if sma20_values else None
    bb_window = closes[-20:]
    bb_mid = sum(bb_window) / len(bb_window) if len(bb_window) == 20 else None
    bb_std = (sum((value - bb_mid) ** 2 for value in bb_window) / len(bb_window)) ** 0.5 if bb_mid is not None else None
    bb_high = max(indicator_highs[-20:]) if len(indicator_highs) >= 20 else None
    bb_low = min(indicator_lows[-20:]) if len(indicator_lows) >= 20 else None
    stochastic_values: list[float] = []
    for end_index in range(max(13, len(indicator_closes) - 22), len(indicator_closes)):
        hi_window = indicator_highs[end_index - 13:end_index + 1]
        lo_window = indicator_lows[end_index - 13:end_index + 1]
        hi_value, lo_value = max(hi_window), min(lo_window)
        stochastic_values.append((indicator_closes[end_index] - lo_value) / (hi_value - lo_value) * 100.0 if hi_value > lo_value else 50.0)
    return {
        # Canonical names are kept for the quant engine; aliases below match
        # the Flutter pages' documented schema so all tabs render the same data.
        "ema_fast_8": fast_line[-1], "ema_slow_21": slow_line[-1],
        "ema_fast": fast_line[-1], "ema_slow": slow_line[-1],
        "ema_alignment": "BULLISH" if fast_line[-1] > slow_line[-1] else "BEARISH" if fast_line[-1] < slow_line[-1] else "NEUTRAL",
        "rsi_14": round(rsi, 2), "rsi14": round(rsi, 2), "rsi": round(rsi, 2),
        "sma_20": sma20, "sma20": sma20,
        "sma_50": sma50_values[-1] if sma50_values else None,
        "ema50": ema50_values[-1] if ema50_values else None,
        "ema200": ema200_values[-1] if ema200_values else None,
        "rsi_reversion_signal": reversion_values[-1] if reversion_values else "WAIT",
        "macd_line": round(macd_line[-1], 4) if macd_line else None,
        "macd": round(macd_line[-1], 4) if macd_line else None,
        "macd_signal": round(macd_signal[-1], 4) if macd_signal else None,
        "macd_histogram": round(macd_histogram, 4) if macd_histogram is not None else None,
        "macd_hist": round(macd_histogram, 4) if macd_histogram is not None else None,
        "underlying_atr_14": atr_values[-1] if atr_values and atr_values[-1] is not None else None,
        "atr14": atr_values[-1] if atr_values and atr_values[-1] is not None else None,
        "vwap": vwap_numerator / vwap_denominator if vwap_denominator > 0 else None,
        "vwap_source": "session OHLCV" if vwap_denominator > 0 else "UNAVAILABLE_NO_VOLUME",
        "bb_mid": bb_mid, "bb_upper": bb_mid + 2 * bb_std if bb_mid is not None and bb_std is not None else None,
        "bb_lower": bb_mid - 2 * bb_std if bb_mid is not None and bb_std is not None else None,
        "stochastic_k14": stochastic_values[-1] if stochastic_values else None,
        "stochastic_d3": sum(stochastic_values[-3:]) / 3 if len(stochastic_values) >= 3 else None,
        "williams_r14": -100 * (max(indicator_highs[-14:]) - indicator_closes[-1]) / (max(indicator_highs[-14:]) - min(indicator_lows[-14:])) if len(indicator_closes) >= 14 and max(indicator_highs[-14:]) > min(indicator_lows[-14:]) else None,
        "roc10_pct": ((closes[-1] / closes[-11]) - 1) * 100 if len(closes) >= 11 and closes[-11] else None,
        "support20": min(indicator_lows[-20:]) if len(indicator_lows) >= 20 else None,
        "resistance20": max(indicator_highs[-20:]) if len(indicator_highs) >= 20 else None,
        "zscore20": (closes[-1] - bb_mid) / bb_std if bb_mid is not None and bb_std not in (None, 0) else None,
        "realized_vol20": ((sum((((closes[i] / closes[i - 1]) - 1) ** 2) for i in range(len(closes) - 20, len(closes))) / 20) ** 0.5) * 100 if len(closes) >= 21 else None,
        # ADX and Supertrend are intentionally null until a separately tested
        # implementation is available; the UI must not invent these values.
        "adx14": None, "supertrend_direction": None,
    }


def _atr_from_candles(rows: list[Any], period: int = 14) -> float | None:
    true_ranges: list[float] = []
    previous_close: float | None = None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        high, low, close = _number(row[2]), _number(row[3]), _number(row[4])
        if high is None or low is None or close is None or high < low:
            continue
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)) if previous_close is not None else high - low)
        previous_close = close
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:]) / period


def _session_range() -> tuple[str, str]:
    now_ist = datetime.now(IST)
    start = datetime.combine(now_ist.date() - timedelta(days=1), dt_time(9, 15), tzinfo=IST)
    end = now_ist
    return start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M")


def _wait_signal(index: str, reason: str) -> dict[str, Any]:
    return {
        "decision": "WAIT", "candidate_decision": "WAIT", "index": index,
        "entry": None, "stop_loss": None, "target": None, "strike": None,
        "expiry": None, "signal_only": True, "layers": {},
        "reasons": [reason], "signal_stability": {"state": "BLOCKED", "required_minutes": 10},
        "data_source": "angelone_smartapi", "data_fresh": False,
    }


def _greeks_map(adapter: AngelOneReadOnly, name: str, expiry: str) -> dict[tuple[float, str], dict[str, float | None]]:
    # SmartAPI optionGreek is an NSE endpoint; BSE indices (SENSEX/BANKEX)
    # routinely return AB9019 "No Data Available". Do not call it for BSE.
    if name.strip().upper() in {"SENSEX", "BANKEX"}:
        return {}
    try:
        data = adapter.option_greeks(name, expiry).get("data") or []
    except Exception:
        return {}
    mapped: dict[tuple[float, str], dict[str, float | None]] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        strike = _number(row.get("strikePrice") or row.get("strike"))
        if strike is None:
            continue
        kind = str(row.get("optionType") or row.get("optiontype") or "").upper()
        kind = "CALL" if kind in ("CE", "CALL") else "PUT" if kind in ("PE", "PUT") else ""
        if not kind:
            continue
        mapped[(strike, kind)] = {
            "delta": _number(row.get("delta")),
            "gamma": _number(row.get("gamma")),
            "theta": _number(row.get("theta")),
            "vega": _number(row.get("vega")),
            "iv": _number(row.get("impliedVolatility") or row.get("impliedvolatility") or row.get("iv")),
        }
    return mapped


def _market_chain_rows(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map normalized live quotes to the Flutter option-chain schema.

    OI and premium changes are deltas between observed snapshots, not invented
    values. The first observation has null changes until a prior quote exists.
    """
    now = _utc_now()
    output: list[dict[str, Any]] = []
    for item in options:
        token = str(item.get("token") or "")
        ltp = _number(item.get("ltp"))
        oi = _number(item.get("oi"))
        previous = _option_history.get(token, {}) if token else {}
        oi_change = oi - previous["oi"] if oi is not None and previous.get("oi") is not None else None
        premium_change = (ltp - previous["ltp"]) / previous["ltp"] if ltp is not None and previous.get("ltp") not in (None, 0) else None
        if token and (ltp is not None or oi is not None):
            _option_history[token] = {"ltp": ltp, "oi": oi}  # type: ignore[dict-item]
        stamp = _iso(item.get("timestamp"))
        parsed = datetime.fromisoformat(stamp) if stamp else None
        age = (now - parsed).total_seconds() if parsed else None
        kind = str(item.get("option_type") or "").upper()
        output.append({
            "symbol": item.get("symbol"), "token": token,
            "side": "CE" if kind == "CALL" else "PE" if kind == "PUT" else None,
            "option_type": kind, "strike": item.get("strike"), "expiry": item.get("expiry"),
            "ltp": ltp, "bid": item.get("bid"), "ask": item.get("ask"),
            "volume": item.get("volume"), "oi": oi, "oi_change": oi_change,
            "premium_change": premium_change, "iv": item.get("iv"),
            "delta": item.get("delta"), "gamma": item.get("gamma"),
            "theta": item.get("theta"), "vega": item.get("vega"),
            "age_seconds": round(age, 2) if age is not None else None,
            "timestamp": stamp, "source_timestamp": stamp,
            "live": age is not None and 0 <= age <= 60,
            "buy_depth": item.get("buy_depth"), "sell_depth": item.get("sell_depth"),
        })
    return output


def _index_snapshot(adapter: AngelOneReadOnly, rows: list[dict[str, Any]], index: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = _find_index_contract(rows, index)
    start, end = _session_range()
    spot_quote = _quotes(adapter, config["exchange"], [config["token"]]).get(config["token"])
    if not spot_quote:
        raise RuntimeError("Angel One did not return a spot quote for this index")
    spot = _number(spot_quote.get("ltp"))
    if spot is None or spot <= 0:
        raise RuntimeError("Spot LTP is missing or invalid")
    spot_ts = _quote_timestamp(spot_quote)
    if not spot_ts:
        raise RuntimeError("Angel One quote omitted its exchange feed timestamp; fail-closed freshness gate")
    candle_result = adapter.candles(config["exchange"], config["token"], "FIVE_MINUTE", start, end)
    candle_rows = candle_result.get("candles") or []
    closes = _candle_closes(candle_rows)
    if len(closes) < 36:
        raise RuntimeError("Insufficient 5-minute candle history for multi-timeframe trend")
    timeframe_closes = {
        "5m": closes[-80:],
        "15m": _resample_closes(closes, 3),
        "1h": _resample_closes(closes, 12),
    }
    bid, ask, buy_volume, sell_volume = _book(spot_quote)
    # Session structure sentiment is explicitly price/volume-derived, not news sentiment.
    today_ist = datetime.now(IST).date()
    today_rows = []
    for candle in candle_rows:
        if not isinstance(candle, (list, tuple)) or len(candle) < 2:
            continue
        candle_time = _iso(candle[0])
        parsed_time = datetime.fromisoformat(candle_time) if candle_time else None
        if parsed_time is not None and parsed_time.astimezone(IST).date() == today_ist:
            today_rows.append(candle)
    day_open = _number(today_rows[0][1]) if today_rows else closes[-1]
    day_move = (spot - day_open) / day_open if day_open else 0.0
    today_highs = [_number(row[2]) for row in today_rows if len(row) > 2]
    today_lows = [_number(row[3]) for row in today_rows if len(row) > 3]
    day_high = max((value for value in today_highs if value is not None), default=spot)
    day_low = min((value for value in today_lows if value is not None), default=spot)
    day_range_position = (spot - day_low) / (day_high - day_low) if day_high > day_low else 0.5
    up_count = sum(1 for tf in timeframe_closes.values() if len(tf) >= 3 and tf[-1] > tf[-2] > tf[-3])
    down_count = sum(1 for tf in timeframe_closes.values() if len(tf) >= 3 and tf[-1] < tf[-2] < tf[-3])
    sentiment = 0.0  # Recalculated below from today's price, trend, option OI and order-book depth.
    indicators = _indicator_snapshot(closes, candle_rows, today_rows)
    chain_rows = [
        row for row in rows
        if str(row.get("exch_seg", "")).upper() == ("BFO" if index in ("SENSEX", "BANKEX") else "NFO")
        and str(row.get("name", "")).upper().replace(" ", "") == index
        and str(row.get("instrumenttype", "")).upper() == "OPTIDX"
        and _option_type(row) is not None
        and (_expiry_date(row.get("expiry")) is not None and _expiry_date(row.get("expiry")) >= datetime.now(IST).date())
    ]
    expiries = sorted({_expiry_date(row.get("expiry")) for row in chain_rows if _expiry_date(row.get("expiry"))})
    selected_expiry = expiries[0] if expiries else None
    if selected_expiry is None:
        raise RuntimeError("No unexpired index option contracts found in instrument master")
    expiry_rows = [row for row in chain_rows if _expiry_date(row.get("expiry")) == selected_expiry]
    strike_values = sorted({strike for row in expiry_rows if (strike := _strike_value(row.get("strike"), spot)) is not None})
    if not strike_values:
        raise RuntimeError("Option master has no valid strikes for the selected expiry")
    atm_index = min(range(len(strike_values)), key=lambda i: abs(strike_values[i] - spot))
    wanted_strikes = set(strike_values[max(0, atm_index - 8): min(len(strike_values), atm_index + 9)])
    candidates = [
        row for row in expiry_rows
        if (strike := _strike_value(row.get("strike"), spot)) in wanted_strikes
        and str(row.get("token", "")).strip()
    ]
    if not candidates:
        raise RuntimeError("No near-ATM option tokens found")
    exchange = "BFO" if index in ("SENSEX", "BANKEX") else "NFO"
    option_quotes = _quotes(adapter, exchange, [str(row["token"]) for row in candidates[:40]])
    greek_expiry = selected_expiry.strftime("%d%b%Y").upper()
    greeks = _greeks_map(adapter, index, greek_expiry)
    normalized_options: list[dict[str, Any]] = []
    quote_time_by_token: dict[str, str] = {}
    for row in candidates[:40]:
        token = str(row.get("token", ""))
        quote = option_quotes.get(token)
        if not quote:
            continue
        strike = _strike_value(row.get("strike"), spot)
        kind = _option_type(row)
        ltp = _number(quote.get("ltp"))
        obid, oask, _, _ = _book(quote)
        volume = _number(quote.get("tradeVolume") or quote.get("volume"))
        oi = _number(quote.get("opnInterest") or quote.get("openInterest") or quote.get("oi"))
        greek = greeks.get((strike or -1, kind or ""), {})
        delta = _number(greek.get("delta"))
        timestamp = _quote_timestamp(quote)
        if not timestamp:
            # Never promote the spot timestamp or server fetch time to an option's timestamp.
            continue
        quote_time_by_token[token] = timestamp
        normalized_options.append({
            "token": token, "exchange": exchange, "option_type": kind,
            "strike": strike, "expiry": selected_expiry.isoformat(),
            "symbol": str(row.get("symbol", "")), "bid": obid, "ask": oask,
            "lot_size": _number(row.get("lotsize") or row.get("lot_size")),
            "ltp": ltp, "volume": volume, "oi": oi, "delta": delta,
            "gamma": greek.get("gamma"), "theta": greek.get("theta"),
            "vega": greek.get("vega"), "iv": greek.get("iv"),
            "buy_depth": _book(quote)[2], "sell_depth": _book(quote)[3],
            "timestamp": timestamp,
        })
    call_oi = sum((_number(item.get("oi")) or 0.0) for item in normalized_options if item.get("option_type") == "CALL")
    put_oi = sum((_number(item.get("oi")) or 0.0) for item in normalized_options if item.get("option_type") == "PUT")
    pcr = put_oi / call_oi if call_oi > 0 else None
    depth_total = buy_volume + sell_volume
    depth_imbalance = (buy_volume - sell_volume) / depth_total if depth_total > 0 else 0.0
    day_move_component = max(-0.30, min(0.30, day_move * 10.0))
    trend_component = 0.25 if up_count >= 2 else -0.25 if down_count >= 2 else 0.0
    depth_component = 0.20 * max(-1.0, min(1.0, depth_imbalance))
    pcr_component = 0.15 if pcr is not None and pcr >= 1.10 else -0.15 if pcr is not None and pcr <= 0.80 else 0.0
    range_component = 0.10 * max(-1.0, min(1.0, (day_range_position - 0.5) * 2.0))
    sentiment_components = {
        "day_move": round(day_move_component, 4),
        "multi_timeframe_trend": round(trend_component, 4),
        "top5_depth_imbalance": round(depth_component, 4),
        "option_pcr_bias": round(pcr_component, 4),
        "session_range_position": round(range_component, 4),
    }
    technical_sentiment = max(-1.0, min(1.0, sum(sentiment_components.values())))
    news_sentiment = cached_market_news_sentiment(index)
    news_score = _number(news_sentiment.get("score"))
    sentiment = max(-1.0, min(1.0, technical_sentiment * 0.85 + news_score * 0.15)) if news_score is not None else technical_sentiment
    trend_5 = timeframe_closes["5m"]
    trend = "BULLISH" if len(trend_5) >= 3 and trend_5[-1] > trend_5[-2] > trend_5[-3] else "BEARISH" if len(trend_5) >= 3 and trend_5[-1] < trend_5[-2] < trend_5[-3] else "MIXED"
    preferred_type = "CALL" if trend == "BULLISH" else "PUT" if trend == "BEARISH" else None
    selectable = [item for item in normalized_options if item["option_type"] == preferred_type and item["delta"] is not None and item["bid"] is not None and item["ask"] is not None and item["ltp"] is not None]
    selected = min(selectable, key=lambda item: abs((item["strike"] or spot) - spot)) if selectable else None
    option_atr = None
    if selected:
        option_candles = adapter.candles(exchange, selected["token"], "FIVE_MINUTE", start, end).get("candles") or []
        option_atr = _atr_from_candles(option_candles)
        selected["option_atr"] = option_atr
    # Do not pass a server fetch time off as exchange time; source timestamps are mandatory.
    observed = _iso(spot_ts)
    if not observed:
        raise RuntimeError("Exchange timestamp could not be parsed")
    snapshot = {
        "observed_at": observed,
        "underlying_ltp": spot,
        "sentiment_score": sentiment,
        "timeframe_closes": timeframe_closes,
        "indicators": indicators,
        "order_flow": {"bid": bid, "ask": ask, "ltp": spot, "buy_volume": buy_volume, "sell_volume": sell_volume},
        # Feed the exact contract whose ATR was fetched into the risk gate.
        # Do not let the engine silently choose a different contract with no ATR.
        "option_chain": [
            {key: value for key, value in selected.items() if key not in ("token", "exchange", "symbol")}
        ] if selected and option_atr is not None else [
            {key: value for key, value in item.items() if key not in ("token", "exchange", "symbol")}
            for item in normalized_options
        ],
    }
    # A source timestamp that is missing or older than the freshness gate will
    # make the quant engine return WAIT; do not substitute the local clock.
    result = evaluate_five_layer_signal(
        snapshot,
        confirmation_state=_confirmation_states.get(index),
        max_data_age_seconds=60.0,
        confirmation_seconds=600,
        max_confirmation_gap_seconds=60,
    )
    _confirmation_states[index] = result.get("confirmation_state") or {}
    chain_payload = _market_chain_rows(normalized_options)
    result.update({
        "index": index, "data_source": "angelone_smartapi",
        "data_fresh": result.get("layers", {}).get("data_quality", {}).get("pass") is True,
        "sentiment_source": "intraday OHLC + multi-timeframe trend + option OI PCR + top-five bid/ask depth" + (" + last-24h Exa/Tavily headlines" if news_score is not None else ""),
        "technical_sentiment_score": technical_sentiment,
        "news_sentiment": news_sentiment,
        "day_move_pct": round(day_move * 100, 3),
        "indicator_summary": {"timeframes": timeframe_closes, "five_minute_trend": trend, **indicators},
        "option_chain_count": len(normalized_options),
        "signal_stability": {
            "state": result.get("layers", {}).get("confirmation", {}).get("state", "BLOCKED"),
            "required_minutes": 10,
            "required_seconds": 600,
        },
    })
    if selected:
        result["strike"] = selected["strike"] if result.get("strike") is not None else None
        result["expiry"] = selected["expiry"] if result.get("expiry") is not None else None
    result["reason"] = list(result.get("reasons") or [])
    result["guards"] = list(result.get("reasons") or [])
    result["option_side"] = "CE" if result.get("option_type") == "CALL" else "PE" if result.get("option_type") == "PUT" else None
    result["confidence"] = None  # No calibrated probability model is available.
    result["timeframe_analysis"] = {
        "entry_timeframe": "5m", "setup_timeframe": "5m", "regime_timeframe": "15m",
        "research_pack": {
            "candidate_alignment": result.get("layers", {}).get("trend_sentiment", {}).get("trend", "UNKNOWN"),
            "evidence_score": None,
            "checks": {
                "trend_following": {"state": result.get("layers", {}).get("trend_sentiment", {}).get("trend", "UNKNOWN")},
                "mean_reversion": {"state": "NOT_COMPUTED"},
                "option_oi_premium_flow": {"state": "PARTIAL" if normalized_options else "UNKNOWN"},
                "execution_liquidity": {"state": "PASS" if result.get("layers", {}).get("option_selection", {}).get("pass") else "BLOCKED"},
            },
            "safety_note": "Deterministic gates only; no calibrated win probability or news sentiment.",
        },
    }
    selected_expiry_date = _expiry_date(selected.get("expiry")) if selected else None
    result["trade_plan"] = {
        "selection_grade": "A" if result.get("decision") in ("CALL BUY", "PUT BUY") else "WAIT",
        "dte": max(0, (selected_expiry_date - datetime.now(IST).date()).days) if selected_expiry_date else None,
        "lot_size": selected.get("lot_size") if selected else None,
        "strike": result.get("strike"),
        "expiry": result.get("expiry"),
        "entry": result.get("entry"),
        "stop_loss": result.get("stop_loss"),
        "target": result.get("target"),
        "signal_only": True,
    }
    result["live_validation"] = {
        "decision": result.get("decision", "WAIT"),
        "verdict": "PASS" if result.get("decision") in ("CALL BUY", "PUT BUY") else "WARN",
        "market_direction": result.get("layers", {}).get("trend_sentiment", {}).get("trend", "UNKNOWN"),
        "market_age_seconds": result.get("layers", {}).get("data_quality", {}).get("age_seconds"),
        "option_age_seconds": next((item.get("age_seconds") for item in chain_payload if item.get("strike") == result.get("strike")), None),
        "ai_decision": "NOT_CONFIGURED",
        "blocks": list(result.get("reasons") or []),
    }
    chart_5m: list[dict[str, Any]] = []
    for candle in candle_rows:
        if not isinstance(candle, (list, tuple)) or len(candle) < 6:
            continue
        stamp = _iso(candle[0])
        parsed_stamp = datetime.fromisoformat(stamp) if stamp else None
        opened, high, low, closed = (_number(candle[i]) for i in (1, 2, 3, 4))
        if parsed_stamp is None or any(value is None for value in (opened, high, low, closed)):
            continue
        chart_5m.append({
            "t": int(parsed_stamp.timestamp()), "timestamp": stamp,
            "open": opened, "high": high, "low": low, "close": closed,
            "volume": _number(candle[5]),
        })
    chart_5m = chart_5m[-250:]
    chart_15m: list[dict[str, Any]] = []
    for offset in range(0, len(chart_5m) - 2, 3):
        group = chart_5m[offset:offset + 3]
        if len(group) != 3:
            continue
        volumes = [_number(row.get("volume")) for row in group]
        chart_15m.append({
            "t": group[-1]["t"], "timestamp": group[-1]["timestamp"],
            "open": group[0]["open"], "high": max(row["high"] for row in group),
            "low": min(row["low"] for row in group), "close": group[-1]["close"],
            "volume": sum(value for value in volumes if value is not None) if any(value is not None for value in volumes) else None,
        })
    result["indicators"] = indicators
    result["oi_summary"] = {
        "call_oi": call_oi, "put_oi": put_oi, "pcr": pcr,
        "classification": "PUT OI HEAVY" if pcr is not None and pcr >= 1.10 else "CALL OI HEAVY" if pcr is not None and pcr <= 0.80 else "BALANCED" if pcr is not None else "DATA REQUIRED",
        "selected_oi_regime": "PUT OI HEAVY" if pcr is not None and pcr >= 1.10 else "CALL OI HEAVY" if pcr is not None and pcr <= 0.80 else "BALANCED" if pcr is not None else "DATA REQUIRED",
    }
    market = {
        "ltp": spot, "age_seconds": result.get("layers", {}).get("data_quality", {}).get("age_seconds"),
        "feed_mode": spot_quote.get("_source_mode", "REST_FULL_DEPTH"), "source": "angelone_smartapi",
        "source_timestamp": spot_ts, "timestamp": spot_ts,
        "live": result.get("data_fresh") is True, "day_move_pct": round(day_move * 100, 3),
        "sentiment_score": sentiment, "sentiment_label": "BULLISH" if sentiment >= 0.2 else "BEARISH" if sentiment <= -0.2 else "NEUTRAL",
        "sentiment_source": "intraday OHLC + multi-timeframe trend + option OI PCR + top-five bid/ask depth" + (" + last-24h Exa/Tavily headlines" if news_score is not None else ""),
        "technical_sentiment_score": technical_sentiment,
        "news_sentiment": news_sentiment,
        "sentiment_components": sentiment_components, "pcr": pcr,
        "session_open": day_open, "session_high": day_high, "session_low": day_low,
        "session_range_position": round(day_range_position, 4),
        "depth_imbalance": round(depth_imbalance, 4),
        "order_flow": {
            "bid": bid, "ask": ask, "buy_volume": buy_volume, "sell_volume": sell_volume,
            "depth_imbalance": depth_imbalance,
            "semantics": "bid_ask_depth_not_classified_trade_volume",
        },
        "indicators": indicators,
        "timeframes": {"1m": [], "5m": chart_5m, "15m": chart_15m},
        "option_chain": chain_payload,
    }
    return result, market


def _empty_payload(reason: str) -> dict[str, Any]:
    now = _utc_now().isoformat()
    return {
        "live": False, "last_fetch": None,
        "feed": {"authenticated": False, "connected": False, "mode": "REST_FULL_DEPTH", "message": reason, "stream_started": False, "stream_open": False, "tick_count": 0, "unique_tokens_seen": 0, "last_tick_age_seconds": None, "last_error": reason},
        "store": {"source": "angelone_smartapi", "fresh": False, "message": reason, "update_count": 0, "last_update_age_seconds": None, "unique_tokens": 0},
        "ai": {"status": "not_configured", "message": "AI validation is not used to fabricate market data."},
        "market": {key: {"ltp": None, "age_seconds": None, "feed_mode": "NO_DATA"} for key in INDEXES},
        "signals": {key: _wait_signal(key, reason) for key in INDEXES},
        "trade_plans": [], "qualified_trade_count": 0,
        "commodities": [{"symbol": name, "status": "WAIT", "reason": reason, "ltp": None} for name in COMMODITY_NAMES],
        "generated_at": now, "signal_only": True, "order_placement_enabled": False,
    }


@app.websocket("/ws")
async def market_snapshot_stream(websocket: WebSocket) -> None:
    """Stream only broker-sourced spot snapshots; never fabricate market ticks.

    The Flutter footprint view receives sampled quotes, not exchange trade prints.
    Depth-derived delta is explicitly labelled as bid/ask depth, not aggressor volume.
    """
    await websocket.accept()
    symbol = (websocket.query_params.get("symbol") or "NIFTY").strip().upper()
    if symbol not in INDEXES:
        await websocket.send_json({"type": "status", "mode": "WAIT", "message": "Unsupported index symbol"})
        await websocket.close(code=1008)
        return
    candles: list[dict[str, Any]] = []
    last_source_timestamp: str | None = None
    try:
        while True:
            try:
                payload = await asyncio.to_thread(_get_signals, False)
                market_row = dict((payload.get("market") or {}).get(symbol) or {})
                ltp = _number(market_row.get("ltp"))
                source_timestamp = _iso(market_row.get("source_timestamp") or market_row.get("timestamp"))
                parsed = datetime.fromisoformat(source_timestamp) if source_timestamp else None
                age = (_utc_now() - parsed).total_seconds() if parsed else None
                live = ltp is not None and ltp > 0 and age is not None and 0 <= age <= 60 and market_row.get("live") is True
                if live and source_timestamp and source_timestamp != last_source_timestamp:
                    flow = dict(market_row.get("order_flow") or {})
                    bid_depth = _number(flow.get("buy_volume")) or 0.0
                    ask_depth = _number(flow.get("sell_volume")) or 0.0
                    epoch = int(parsed.timestamp()) if parsed else 0
                    candles.append({
                        "t": epoch, "o": ltp, "h": ltp, "l": ltp, "c": ltp,
                        "v": bid_depth + ask_depth, "d": bid_depth - ask_depth,
                        "source_timestamp": source_timestamp,
                        "volume_semantics": "bid_ask_depth_not_trade_volume",
                    })
                    candles = candles[-250:]
                    last_source_timestamp = source_timestamp
                await websocket.send_json({
                    "type": "snap", "symbol": symbol, "candles": candles,
                    "mode": "LIVE" if live else "WAIT",
                    "live": live, "ltp": ltp if live else None,
                    "source_timestamp": source_timestamp,
                    "tick_age_ms": int(age * 1000) if age is not None else None,
                    "message": "Broker timestamped snapshots; delta is bid/ask depth, not classified trade prints.",
                    "signal_only": True, "order_placement_enabled": False,
                })
            except HTTPException as exc:
                await websocket.send_json({"type": "status", "mode": "WAIT", "message": str(exc.detail)[:180], "candles": candles})
            except Exception:
                await websocket.send_json({"type": "status", "mode": "WAIT", "message": "Broker snapshot unavailable; waiting for a fresh timestamped quote.", "candles": candles})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "ai-trading-readonly-api", "time": _utc_now().isoformat()}


@app.get("/v1/metadata")
def metadata(_: str = Depends(_device)) -> dict[str, Any]:
    return {
        "service": "AI-TRADING Read-only Signals API", "version": "1.0.0",
        "indexes": list(INDEXES), "commodities": list(COMMODITY_NAMES),
        "signal_only": True, "order_placement_enabled": False,
        "engine": "five-layer fail-closed quant engine", "minimum_confirmation_seconds": 600,
        "credentials_location": "encrypted server-side settings or Railway variables; never APK",
    }


@app.get("/v1/angel/status")
def angel_status(_: str = Depends(_device)) -> dict[str, Any]:
    adapter = _current_adapter()
    status = adapter.status() if adapter else {
        "authenticated": False, "has_jwt_token": False, "has_feed_token": False,
        "client_code": None, "session_age_seconds": None, "source": "angelone_smartapi",
    }
    path = _credential_path()
    saved = path.is_file()
    stream_status = _stream.status() if _stream is not None else {"stream_started": False, "stream_open": False, "tick_count": 0, "unique_tokens_seen": 0, "last_tick_age_seconds": None, "last_error": _stream_start_error}
    return {
        **status,
        **stream_status,
        "stored_session": bool(status.get("authenticated")),
        "stored_credentials": saved,
        "stored_api_key": saved,
        "stored_pin": saved,
        "message": "Authenticated read-only session" if status.get("authenticated") else "Not connected; connect with current TOTP",
    }


@app.post("/v1/angel/connect")
def angel_connect(body: ConnectRequest, _: str = Depends(_device)) -> dict[str, Any]:
    global _adapter, _signal_cache, _signal_cache_at
    supplied = {
        "angel_api_key": (body.angel_api_key or "").strip(),
        "angel_client_code": (body.angel_client_code or "").strip(),
        "angel_pin": (body.angel_pin or "").strip(),
        "angel_totp_code": (body.angel_totp or "").strip(),
    }
    with _lock:
        if _adapter and _adapter.authenticated and not any(supplied.values()):
            if not body.remember_credentials:
                _forget_credentials()
            return {**_adapter.status(), "session_restored": True, "stored_session": True, "stored_credentials": _credential_path().is_file(), "login_message": "Existing in-memory session is authenticated"}
        saved = _load_credentials()
        env = _credentials_from_env()
        base = {**saved, **env}
        for key in ("angel_api_key", "angel_client_code", "angel_pin"):
            supplied[key] = supplied.get(key) or base.get(key, "")
        # A direct six-digit code from the app takes precedence. If no code is
        # supplied, server-side ANGEL_TOTP_SECRET may generate the current code.
        if not supplied.get("angel_totp_code"):
            supplied["angel_totp_secret"] = base.get("angel_totp_secret", "")
        if not all(supplied.get(key) for key in ("angel_api_key", "angel_client_code", "angel_pin")) or not (supplied.get("angel_totp_code") or supplied.get("angel_totp_secret")):
            raise HTTPException(status_code=422, detail="Enter API key, Client ID, MPIN and current six-digit TOTP (or configure ANGEL_TOTP_SECRET in Railway).")
        if body.remember_credentials:
            # Validate key and writable persistent path before contacting broker.
            _encryption_key()
            try:
                _credential_path().parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Remember credentials requires a writable persistent volume at /data.") from exc
        adapter = AngelOneReadOnly(supplied)
        try:
            profile = adapter.profile()
        except AngelOneConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            # Log the exception class only. Exception text and tracebacks can
            # contain broker payloads, request URLs, headers, or credential data.
            # Do not log raw SDK exceptions; they may contain broker payloads or secrets.
            # Classify transport failures without returning raw exception text.
            error_text = str(exc)
            exc_type = type(exc).__name__.lower()
            exc_module = type(exc).__module__.lower()
            # Keep useful SDK diagnostics while redacting submitted credentials,
            # OTP seeds/codes, JWT-like values, and header-style secret fields.
            safe_error_text = error_text
            for secret in list(supplied.values()) + list(base.values()):
                if isinstance(secret, str) and len(secret) >= 4:
                    safe_error_text = safe_error_text.replace(secret, "[redacted]")
            safe_error_text = re.sub(
                r"(?i)(?:eyJ[a-zA-Z0-9_=-]{12,}\.[a-zA-Z0-9_=-]{12,}(?:\.[a-zA-Z0-9_=-]{8,})?|Bearer\s+\S+)",
                "[redacted-token]", safe_error_text,
            )
            safe_error_text = re.sub(
                r"(?i)(api[_ -]?key|authorization|password|pin|totp|refresh[_ -]?token|feed[_ -]?token|jwt[_ -]?token)\s*[:=]\s*[^,;\s]+",
                r"\1=[redacted]", safe_error_text,
            )
            safe_error_text = re.sub(r"[^A-Za-z0-9 .,;:_()/-]", " ", safe_error_text)[:180].strip()
            logger.warning(
                "Angel One connect failed; exception_type=%s module=%s diagnostic=%s",
                type(exc).__name__, type(exc).__module__, safe_error_text or "unavailable",
            )
            transport_error = any(
                name in exc_type or name in exc_module
                for name in ("timeout", "connection", "ssl", "socket", "network", "httpx", "urllib3")
            )
            if transport_error:
                detail = {
                    "message": "Railway could not complete the request to Angel One SmartAPI.",
                    "stage": "smartapi_transport",
                    "error_code": type(exc).__name__[:32],
                    "next_step": "Check Railway outbound HTTPS/DNS/TLS connectivity and retry. If transport succeeds, inspect the sanitized broker response stage.",
                }
                raise HTTPException(status_code=502, detail=detail) from exc
            match = re.search(r"Angel One SmartAPI error \(([^)]+)\): (.*)", error_text)
            if match:
                error_code = match.group(1)[:32]
                safe_message = re.sub(r"[^A-Za-z0-9 .,;:_-]", "", match.group(2))[:180].strip()
                detail = {
                    "message": "Angel One login rejected by SmartAPI.",
                    "stage": "smartapi_authentication",
                    "error_code": error_code,
                    "broker_message": safe_message or "SmartAPI returned an authentication error.",
                    "next_step": "Verify Client ID, MPIN, current TOTP, API key access and system clock.",
                }
            elif "no refresh token" in error_text.lower() or "sdk version" in error_text.lower():
                detail = {
                    "message": "Angel One login response did not provide a usable session token.",
                    "stage": "session_token_extraction",
                    "next_step": "Check the deployed smartapi-python version and token fields returned by SmartAPI.",
                }
            else:
                # Network errors and unexpected SDK exceptions stay generic; never
                # return exception text that could contain request headers or secrets.
                detail = {
                    "message": "Angel One login failed before session verification. Diagnostic: " + (safe_error_text or "No safe diagnostic text was available."),
                    "stage": "broker_request_or_profile_verification",
                    "error_type": type(exc).__name__[:64],
                    "error_module": type(exc).__module__[:100],
                    "diagnostic": safe_error_text or "No safe diagnostic text was available.",
                    "next_step": "Use the diagnostic to distinguish a broker authentication rejection from an SDK/profile failure; do not share API keys, PINs, OTPs, or tokens.",
                }
            raise HTTPException(status_code=502, detail=detail) from exc
        status = adapter.status()
        if not status["has_jwt_token"] or not status["has_feed_token"]:
            raise HTTPException(status_code=502, detail="Profile login succeeded but JWT/feed token readiness was not verified. Check SmartAPI SDK version/session response.")
        if body.remember_credentials:
            _save_credentials(supplied)
        else:
            _forget_credentials()
        _adapter = adapter
        _signal_cache = None
        _signal_cache_at = 0.0
        stream_status = _start_stream(adapter)
        return {
            **status, **stream_status, "authenticated": True, "session_restored": False,
            "stored_session": True, "stored_credentials": body.remember_credentials,
            "login_message": "Angel One authenticated; JWT and feed token verified. No order-placement API is enabled.",
            "profile": {"client_code": profile.get("client_code"), "name": profile.get("name")},
        }


@app.get("/v1/system/diagnostics")
def diagnostics(_: str = Depends(_device)) -> dict[str, Any]:
    adapter = _current_adapter()
    angel = adapter.status() if adapter else {"authenticated": False, "has_jwt_token": False, "has_feed_token": False}
    fresh_count = sum(1 for row in (_signal_cache or {}).get("market", {}).values() if row.get("live") is True)
    return {
        "service": "ai-trading-readonly-api",
        "angel": angel,
        "angel_one": {
            "authenticated": angel.get("authenticated", False),
            "stream_open": bool(_stream and _stream.status().get("stream_open")),
            "last_tick_age_seconds": _stream.status().get("last_tick_age_seconds") if _stream else None,
            "last_error": None if angel.get("authenticated") else "Angel One session is not authenticated",
            "stream_error": (_stream.status().get("last_error") if _stream else _stream_start_error),
        },
        "backend": {
            "cycle_age_seconds": round(time.monotonic() - _signal_cache_at, 1) if _signal_cache else None,
            "cycle_fresh": bool(_signal_cache and time.monotonic() - _signal_cache_at < SIGNAL_CACHE_SECONDS),
        },
        "instrument_master": {"row_count": len(_master_rows), "cached": bool(_master_rows)},
        "market_data": {
            "snapshot_count": len((_signal_cache or {}).get("market", {})),
            "fresh_snapshot_count": fresh_count, "live_snapshot_count": fresh_count,
        },
        "ai": {"configured": False, "model": "deterministic-five-layer", "error_indexes": []},
        "credentials_encryption_configured": bool(os.getenv("CREDENTIALS_ENCRYPTION_KEY")),
        "persistent_credential_file_configured": _credential_path().parent.exists(),
        "instrument_master_cached": bool(_master_rows),
        "last_signal_fetch": _signal_cache.get("last_fetch") if _signal_cache else None,
        "signal_only": True, "order_placement_enabled": False,
    }


@app.post("/v1/instruments/sync")
def sync_instruments(_: str = Depends(_device)) -> dict[str, Any]:
    rows = _load_master(force=True)
    return {
        "status": "ok", "source": "Angel One OpenAPI instrument master",
        "instrument_count": len(rows), "cached_hours": MASTER_TTL_SECONDS // 3600,
        "index_contracts": {key: _find_index_contract(rows, key) for key in INDEXES},
        "synced_at": _utc_now().isoformat(),
    }


@app.post("/v1/stream/start")
def start_stream(body: dict[str, Any], _: str = Depends(_device)) -> dict[str, Any]:
    adapter = _require_adapter()
    requested = [str(item).upper() for item in body.get("indexes", []) if str(item).upper() in INDEXES]
    rows = _load_master()
    status = _start_stream(adapter, rows)
    return {
        **status, "started": status.get("stream_started") is True,
        "mode": "WEBSOCKET_V2_WITH_REST_FALLBACK",
        "indexes": requested or list(INDEXES), "authenticated": adapter.authenticated,
        "message": "SmartWebSocketV2 is requested; live status turns green only after fresh exchange-timestamped ticks. REST FULL-depth fallback remains available.",
    }


@app.get("/v1/live/status")
def live_status(_: str = Depends(_device)) -> dict[str, Any]:
    adapter = _current_adapter()
    connected = bool(adapter and adapter.authenticated)
    stream_status = _stream.status() if _stream is not None else {"stream_started": False, "stream_open": False, "tick_count": 0, "unique_tokens_seen": 0, "last_tick_age_seconds": None, "last_error": _stream_start_error}
    return {
        **stream_status,
        "authenticated": connected, "live": bool(_signal_cache and _signal_cache.get("live")),
        "feed_mode": "WEBSOCKET_V2" if stream_status.get("stream_open") else ("REST_FULL_DEPTH_FALLBACK" if connected else "NO_FEED"),
        "order_placement_enabled": False, "signal_only": True,
        "last_fetch": _signal_cache.get("last_fetch") if _signal_cache else None,
    }


@app.get("/v1/market/ticks")
def market_ticks(_: str = Depends(_device)) -> dict[str, Any]:
    return {"source": "angelone_smartapi", "ticks": _last_market, "count": len(_last_market), "observed_at": _utc_now().isoformat()}


@app.get("/v1/option-chain")
def option_chain(index: str = Query(default="NIFTY"), _: str = Depends(_device)) -> dict[str, Any]:
    index = index.strip().upper()
    if index not in INDEXES:
        raise HTTPException(status_code=400, detail=f"Unsupported index. Choose from {', '.join(INDEXES)}.")
    adapter = _require_adapter()
    rows = _load_master()
    config = _find_index_contract(rows, index)
    spot_quote = _quotes(adapter, config["exchange"], [config["token"]]).get(config["token"])
    spot = _number(spot_quote.get("ltp")) if spot_quote else None
    if spot is None:
        raise HTTPException(status_code=502, detail="Angel One spot quote is missing")
    segment = "BFO" if index in ("SENSEX", "BANKEX") else "NFO"
    contracts = [
        row for row in rows
        if str(row.get("exch_seg", "")).upper() == segment
        and str(row.get("name", "")).upper().replace(" ", "") == index
        and str(row.get("instrumenttype", "")).upper() == "OPTIDX"
        and _option_type(row) is not None
        and _expiry_date(row.get("expiry")) is not None
        and _expiry_date(row.get("expiry")) >= datetime.now(IST).date()
    ]
    expiries = sorted({_expiry_date(row.get("expiry")) for row in contracts if _expiry_date(row.get("expiry"))})
    if not expiries:
        return {"index": index, "spot": spot, "contracts": [], "status": "WAIT", "reason": "No unexpired option contracts found"}
    contracts = [row for row in contracts if _expiry_date(row.get("expiry")) == expiries[0]]
    strikes = sorted({strike for row in contracts if (strike := _strike_value(row.get("strike"), spot)) is not None})
    atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot)) if strikes else 0
    wanted = set(strikes[max(0, atm - 10): min(len(strikes), atm + 11)])
    contracts = [row for row in contracts if _strike_value(row.get("strike"), spot) in wanted][:100]
    quote_map = _quotes(adapter, segment, [str(row.get("token", "")) for row in contracts if row.get("token")])
    greek_map = _greeks_map(adapter, index, expiries[0].strftime("%d%b%Y").upper())
    output = []
    for row in contracts:
        token = str(row.get("token", ""))
        quote = quote_map.get(token)
        if not quote:
            continue
        strike = _strike_value(row.get("strike"), spot)
        kind = _option_type(row)
        bid, ask, buy_depth, sell_depth = _book(quote)
        output.append({
            "symbol": row.get("symbol"), "token": token, "option_type": kind,
            "strike": strike, "expiry": expiries[0].isoformat(),
            "ltp": _number(quote.get("ltp")), "bid": bid, "ask": ask,
            "volume": _number(quote.get("tradeVolume") or quote.get("volume")),
            "oi": _number(quote.get("opnInterest") or quote.get("openInterest") or quote.get("oi")),
            "delta": (greek_map.get((strike or -1, kind or "")) or {}).get("delta"),
            "gamma": (greek_map.get((strike or -1, kind or "")) or {}).get("gamma"),
            "theta": (greek_map.get((strike or -1, kind or "")) or {}).get("theta"),
            "vega": (greek_map.get((strike or -1, kind or "")) or {}).get("vega"),
            "iv": (greek_map.get((strike or -1, kind or "")) or {}).get("iv"),
            "buy_depth": buy_depth, "sell_depth": sell_depth,
            "timestamp": _quote_timestamp(quote), "source_timestamp": _quote_timestamp(quote),
        })
    return {"index": index, "spot": spot, "expiry": expiries[0].isoformat(), "contracts": output, "option_chain": _market_chain_rows(output), "source": "angelone_smartapi", "observed_at": _utc_now().isoformat(), "signal_only": True}


@app.get("/v1/market/sentiment")
def market_sentiment(index: str = Query(default="NIFTY"), _: str = Depends(_device)) -> dict[str, Any]:
    payload = _get_signals(force=False)
    key = index.strip().upper()
    if key not in INDEXES:
        raise HTTPException(status_code=400, detail=f"Unsupported index. Choose from {', '.join(INDEXES)}.")
    signal = payload["signals"].get(key, {})
    market = payload["market"].get(key, {})
    news = fetch_market_news_sentiment(
        key, exa_api_key=os.getenv("EXA_API_KEY"), tavily_api_key=os.getenv("TAVILY_API_KEY")
    )
    return {
        "index": key, "sentiment": market.get("sentiment_label", "UNKNOWN"),
        "score": market.get("sentiment_score"), "day_move_pct": market.get("day_move_pct"),
        "trend": (signal.get("indicator_summary") or {}).get("five_minute_trend", "UNKNOWN"),
        "source": "session price structure and order-book depth",
        "news_sentiment": news.get("label", "UNKNOWN"),
        "news_score": news.get("score"),
        "news_status": news.get("status"),
        "news_article_count": news.get("article_count", 0),
        "news_sources": news.get("sources", []),
        "news_evidence": news.get("articles", []),
        "news_window_hours": news.get("window_hours", 24),
        "news_note": "Headline sentiment is contextual only and never overrides deterministic risk gates.",
        "news_errors": news.get("errors", []),
        "observed_at": payload.get("last_fetch"),
    }


def _get_signals(force: bool = False) -> dict[str, Any]:
    global _signal_cache, _signal_cache_at, _last_market
    with _lock:
        if _signal_cache is not None and not force and time.monotonic() - _signal_cache_at < SIGNAL_CACHE_SECONDS:
            return _signal_cache
    adapter = _require_adapter()
    try:
        rows = _load_master()
        _start_stream(adapter, rows)
        _schedule_news_refresh(list(INDEXES))
        signals: dict[str, Any] = {}
        market: dict[str, Any] = {}
        for index in INDEXES:
            try:
                result, quote = _index_snapshot(adapter, rows, index)
                signals[index] = result
                market[index] = quote
            except Exception as exc:
                # Keep independently verified spot data visible even if the
                # heavier signal pipeline fails (e.g. insufficient candles,
                # option Greeks or option ATR). A signal failure must not blank
                # the Market/Dashboard pages or silently become an actionable trade.
                reason = str(exc)[:220]
                signals[index] = _wait_signal(index, reason)
                market_row: dict[str, Any] = {
                    "ltp": None, "age_seconds": None, "feed_mode": "DATA_ERROR",
                    "source": "angelone_smartapi", "live": False,
                    "error": reason, "signal_error": reason, "option_chain": [],
                }
                try:
                    index_config = INDEXES[index]
                    spot_fallback = _quotes(adapter, index_config["exchange"], [index_config["token"]]).get(index_config["token"])
                    if spot_fallback:
                        spot_ltp = _number(spot_fallback.get("ltp"))
                        spot_timestamp = _quote_timestamp(spot_fallback)
                        parsed_spot_timestamp = datetime.fromisoformat(_iso(spot_timestamp)) if spot_timestamp and _iso(spot_timestamp) else None
                        spot_age = (_utc_now() - parsed_spot_timestamp).total_seconds() if parsed_spot_timestamp else None
                        spot_live = spot_ltp is not None and spot_ltp > 0 and spot_age is not None and 0 <= spot_age <= 60
                        bid_fallback, ask_fallback, buy_depth_fallback, sell_depth_fallback = _book(spot_fallback)
                        market_row.update({
                            "ltp": spot_ltp, "age_seconds": round(spot_age, 2) if spot_age is not None else None,
                            "feed_mode": spot_fallback.get("_source_mode", "REST_FULL_DEPTH"),
                            "source": "angelone_smartapi", "source_timestamp": spot_timestamp,
                            "timestamp": spot_timestamp, "live": spot_live,
                            "signal_error": reason,
                            "error": None if spot_live else reason,
                            "order_flow": {
                                "bid": bid_fallback, "ask": ask_fallback,
                                "buy_volume": buy_depth_fallback, "sell_volume": sell_depth_fallback,
                                "semantics": "bid_ask_depth_not_classified_trade_volume",
                            },
                        })
                        # Keep real 5-minute candles available for charting even
                        # when the stricter signal engine rejects this index.
                        try:
                            start_text, end_text = _session_range()
                            candle_payload = adapter.candles(index_config["exchange"], index_config["token"], "FIVE_MINUTE", start_text, end_text)
                            chart_rows: list[dict[str, Any]] = []
                            chart_closes: list[float] = []
                            chart_highs: list[float] = []
                            chart_lows: list[float] = []
                            for candle in candle_payload.get("candles") or []:
                                if not isinstance(candle, (list, tuple)) or len(candle) < 6:
                                    continue
                                candle_stamp = _iso(candle[0])
                                candle_dt = datetime.fromisoformat(candle_stamp) if candle_stamp else None
                                candle_values = [_number(candle[pos]) for pos in (1, 2, 3, 4)]
                                if candle_dt is None or any(value is None for value in candle_values):
                                    continue
                                opened, high, low, closed = candle_values
                                chart_rows.append({
                                    "t": int(candle_dt.timestamp()), "timestamp": candle_stamp,
                                    "open": opened, "high": high, "low": low, "close": closed,
                                    "volume": _number(candle[5]),
                                })
                                chart_closes.append(closed)
                                chart_highs.append(high)
                                chart_lows.append(low)
                            chart_rows = chart_rows[-250:]
                            chart_15m_rows: list[dict[str, Any]] = []
                            for offset in range(0, len(chart_rows) - 2, 3):
                                group = chart_rows[offset:offset + 3]
                                if len(group) == 3:
                                    volumes = [_number(row.get("volume")) for row in group]
                                    chart_15m_rows.append({
                                        "t": group[-1]["t"], "timestamp": group[-1]["timestamp"],
                                        "open": group[0]["open"], "high": max(row["high"] for row in group),
                                        "low": min(row["low"] for row in group), "close": group[-1]["close"],
                                        "volume": sum(value for value in volumes if value is not None) if any(value is not None for value in volumes) else None,
                                    })
                            market_row["timeframes"] = {"1m": [], "5m": chart_rows, "15m": chart_15m_rows}
                            if len(chart_closes) >= 30:
                                market_row["indicators"] = _indicator_snapshot(chart_closes, candle_payload.get("candles") or [], [])
                        except Exception:
                            # Missing history remains missing; the valid spot quote is retained.
                            pass
                except Exception:
                    # Preserve the primary failure; never substitute server time or sample prices.
                    pass
                market[index] = market_row
        commodities = _commodity_snapshot(adapter, rows)
        confirmed = []
        for index, signal in signals.items():
            if signal.get("decision") in ("CALL BUY", "PUT BUY") and signal.get("entry") is not None:
                confirmed.append({
                    "index": index, "side": signal["decision"], "strike": signal.get("strike"),
                    "expiry": signal.get("expiry"), "entry": signal.get("entry"),
                    "stop_loss": signal.get("stop_loss"), "target": signal.get("target"),
                    "timeframe": "5m setup / 10m stable confirmation",
                    "holding_gate_minutes": 10, "signal_only": True,
                    "source": "angelone_smartapi + five_layer_quant_engine",
                })
        live = any(value.get("data_fresh") is True for value in signals.values())
        result = {
            "live": live, "last_fetch": _utc_now().isoformat(),
            "feed": {
                "authenticated": True, "connected": live,
                **(_stream.status() if _stream is not None else {"stream_started": False, "stream_open": False, "tick_count": 0, "unique_tokens_seen": 0, "last_tick_age_seconds": None, "last_error": _stream_start_error}),
                "mode": "WEBSOCKET_V2" if _stream is not None and _stream.status().get("stream_open") else "REST_FULL_DEPTH_FALLBACK",
                "message": "Fresh exchange-timestamped market data" if live else "Connected but no index passed freshness/data gates",
            },
            "store": {"source": "angelone_smartapi", "fresh": live, "index_count": len(signals), "update_count": len(signals), "last_update_age_seconds": 0 if live else None, "unique_tokens": sum(1 for row in market.values() if row.get("ltp") is not None)},
            "ai": {"status": "not_configured", "message": "Deterministic quant gates are authoritative; news/LLM validation is not configured on this service."},
            "market": market, "signals": signals, "trade_plans": confirmed,
            "qualified_trade_count": len(confirmed), "commodities": commodities,
            "generated_at": _utc_now().isoformat(), "signal_only": True,
            "order_placement_enabled": False,
        }
        with _lock:
            _signal_cache = result
            _signal_cache_at = time.monotonic()
            _last_market = market
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Live market collection failed: {str(exc)[:180]}") from exc


def _commodity_snapshot(adapter: AngelOneReadOnly, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Active MCX futures only; live quote status and trend are kept separate
    # from an actionable options signal because commodities may have no option chain.
    today = datetime.now(IST).date()
    start, end = _session_range()
    result = []
    for name in COMMODITY_NAMES:
        contracts = [
            row for row in rows
            if str(row.get("exch_seg", "")).upper() == "MCX"
            and str(row.get("name", "")).upper() == name
            and str(row.get("instrumenttype", "")).upper() == "FUTCOM"
            and _expiry_date(row.get("expiry")) is not None
            and _expiry_date(row.get("expiry")) >= today
            and row.get("token")
        ]
        contracts.sort(key=lambda row: _expiry_date(row.get("expiry")) or date.max)
        if not contracts:
            result.append({"name": name, "symbol": name, "status": "WAIT", "live": False, "reason": "No active MCX futures contract in instrument master", "ltp": None, "source": "angelone_smartapi"})
            continue
        contract = contracts[0]
        try:
            token = str(contract["token"])
            quote = _quotes(adapter, "MCX", [token]).get(token, {})
            ltp = _number(quote.get("ltp"))
            timestamp = _quote_timestamp(quote)
            parsed_timestamp = datetime.fromisoformat(timestamp) if timestamp else None
            age = (_utc_now() - parsed_timestamp).total_seconds() if parsed_timestamp else None
            live = ltp is not None and ltp > 0 and age is not None and 0 <= age <= 60
            bid, ask, buy_depth, sell_depth = _book(quote)
            trend = "UNKNOWN"
            sentiment = None
            sentiment_label = "UNKNOWN"
            indicators: dict[str, Any] = {}
            futures_signal: dict[str, Any] = {
                "decision": "WAIT", "candidate_decision": "WAIT", "entry": None,
                "stop_loss": None, "target": None,
                "signal_stability": {"state": "BLOCKED", "required_minutes": 10},
                "reasons": ["Fresh quote and sufficient candles are required for a futures signal"],
            }
            day_move_pct = None
            session_open = session_high = session_low = None
            reason = None if live else "Quote lacks a fresh exchange timestamp or valid LTP"
            try:
                candle_rows = adapter.candles("MCX", token, "FIVE_MINUTE", start, end).get("candles") or []
                closes = _candle_closes(candle_rows)
                today_rows = []
                for candle in candle_rows:
                    if not isinstance(candle, (list, tuple)) or len(candle) < 5:
                        continue
                    candle_time = _iso(candle[0])
                    parsed_time = datetime.fromisoformat(candle_time) if candle_time else None
                    if parsed_time is not None and parsed_time.astimezone(IST).date() == today:
                        today_rows.append(candle)
                if len(closes) >= 30 and live:
                    trend = "BULLISH" if closes[-1] > closes[-2] > closes[-3] else "BEARISH" if closes[-1] < closes[-2] < closes[-3] else "MIXED"
                    indicators = _indicator_snapshot(closes, candle_rows, today_rows)
                    session_open = _number(today_rows[0][1]) if today_rows else closes[-1]
                    session_high = max((_number(row[2]) or ltp or closes[-1] for row in today_rows), default=ltp or closes[-1])
                    session_low = min((_number(row[3]) or ltp or closes[-1] for row in today_rows), default=ltp or closes[-1])
                    day_move = ((ltp or closes[-1]) - session_open) / session_open if session_open else 0.0
                    day_move_pct = round(day_move * 100, 3)
                    depth_total = buy_depth + sell_depth
                    depth_imbalance = (buy_depth - sell_depth) / depth_total if depth_total > 0 else 0.0
                    sentiment = max(-1.0, min(1.0,
                        (0.35 if trend == "BULLISH" else -0.35 if trend == "BEARISH" else 0.0)
                        + max(-0.30, min(0.30, day_move * 10.0))
                        + 0.20 * max(-1.0, min(1.0, depth_imbalance))
                    ))
                    sentiment_label = "BULLISH" if sentiment >= 0.2 else "BEARISH" if sentiment <= -0.2 else "NEUTRAL"
                    timeframe_closes = {
                        "5m": closes[-80:],
                        "15m": _resample_closes(closes, 3),
                        "1h": _resample_closes(closes, 12),
                    }
                    future_snapshot = {
                        "observed_at": timestamp,
                        "underlying_ltp": ltp,
                        "sentiment_score": sentiment,
                        "timeframe_closes": timeframe_closes,
                        "indicators": indicators,
                        "order_flow": {
                            "bid": bid, "ask": ask, "ltp": ltp,
                            "buy_volume": buy_depth, "sell_volume": sell_depth,
                        },
                        "contract": {
                            "symbol": contract.get("symbol"), "expiry": _expiry_date(contract.get("expiry")).isoformat(),
                            "volume": _number(quote.get("tradeVolume") or quote.get("volume")),
                            "oi": _number(quote.get("opnInterest") or quote.get("openInterest") or quote.get("oi")),
                            "lot_size": _number(contract.get("lotsize") or contract.get("lot_size")),
                        },
                    }
                    confirmation_key = f"MCX_{name}"
                    futures_signal = evaluate_futures_signal(
                        future_snapshot,
                        confirmation_state=_confirmation_states.get(confirmation_key),
                        max_data_age_seconds=60.0,
                        confirmation_seconds=600,
                        max_confirmation_gap_seconds=60,
                    )
                    _confirmation_states[confirmation_key] = futures_signal.get("confirmation_state") or {}
                else:
                    reason = reason or "Quote is live; candle history is insufficient for a trend label"
            except Exception:
                reason = reason or "Quote is live; historical candles are unavailable for trend calculation"
            result.append({
                "name": name, "symbol": str(contract.get("symbol") or name),
                "contract": contract.get("symbol"), "expiry": _expiry_date(contract.get("expiry")).isoformat(),
                "lotsize": contract.get("lotsize") or contract.get("lot_size"),
                "ltp": ltp, "bid": bid, "ask": ask, "buy_depth": buy_depth, "sell_depth": sell_depth,
                "source_timestamp": timestamp, "timestamp": timestamp,
                "age_seconds": round(age, 2) if age is not None else None,
                "source": "angelone_smartapi", "status": "LIVE" if live else "WAIT", "live": live,
                "trend": trend, "sentiment_score": sentiment, "sentiment_label": sentiment_label,
                "day_move_pct": day_move_pct, "session_open": session_open,
                "session_high": session_high, "session_low": session_low,
                "indicators": indicators, "reason": reason,
                **futures_signal,
            })
        except Exception:
            result.append({"name": name, "symbol": str(contract.get("symbol") or name), "status": "WAIT", "live": False, "reason": "Angel One quote/candle request failed", "ltp": None, "source": "angelone_smartapi"})
    return result


@app.post("/v1/research/indicators")
def research_indicators(body: ResearchIndicatorsRequest, _: str = Depends(_device)) -> dict[str, Any]:
    """Run the repository's deterministic indicators on explicitly supplied OHLCV candles.

    Candle row format: [timestamp, open, high, low, close, volume].
    Results are research diagnostics only; no live-data claim or trade order is produced.
    """
    if body.ema_fast >= body.ema_slow:
        raise HTTPException(status_code=422, detail="ema_fast must be smaller than ema_slow")
    rows: list[tuple[str, float, float, float, float, float]] = []
    for i, row in enumerate(body.candles):
        if not isinstance(row, (list, tuple)) or len(row) != 6:
            raise HTTPException(status_code=422, detail=f"candle {i} must contain timestamp, open, high, low, close, volume")
        try:
            stamp = str(row[0])
            o, h, lo, cl, vol = (float(v) for v in row[1:])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"candle {i} contains non-numeric OHLCV data") from None
        if not stamp or any(not __import__("math").isfinite(v) for v in (o, h, lo, cl, vol)):
            raise HTTPException(status_code=422, detail=f"candle {i} contains invalid values")
        if min(o, h, lo, cl) <= 0 or vol < 0 or h < max(o, cl, lo) or lo > min(o, cl, h):
            raise HTTPException(status_code=422, detail=f"candle {i} has inconsistent OHLCV values")
        rows.append((stamp, o, h, lo, cl, vol))
    if any(rows[i][0] >= rows[i + 1][0] for i in range(len(rows) - 1)):
        raise HTTPException(status_code=422, detail="candle timestamps must be strictly increasing")
    closes = [r[4] for r in rows]
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    volumes = [r[5] for r in rows]
    fast = technical_ema(closes, body.ema_fast)
    slow = technical_ema(closes, body.ema_slow)
    rsi_values = technical_rsi(closes, body.rsi_period)
    atr_values = technical_atr(highs, lows, closes, body.atr_period)
    bands = bollinger_bands(closes, body.band_period)
    macd_values = advanced_macd(closes)
    channels = donchian_channels(highs, lows, body.channel_period)
    def latest(series):
        value = series[-1] if series else None
        return round(float(value), 6) if value is not None else None
    last_fast, last_slow = latest(fast), latest(slow)
    trend = "UNKNOWN" if last_fast is None or last_slow is None else ("BULLISH" if last_fast > last_slow else "BEARISH" if last_fast < last_slow else "MIXED")
    return {
        "status": "ok", "source": "caller_supplied_candles", "is_live_verified": False,
        "candle_count": len(rows), "first_timestamp": rows[0][0], "last_timestamp": rows[-1][0],
        "latest": {
            "close": round(closes[-1], 6), "ema_fast": last_fast, "ema_slow": last_slow,
            "trend": trend, "rsi": latest(rsi_values), "atr": latest(atr_values),
            "macd": latest(macd_values["line"]), "macd_signal": latest(macd_values["signal"]),
            "macd_histogram": latest(macd_values["histogram"]),
            "bollinger_lower": latest(bands["lower"]), "bollinger_middle": latest(bands["middle"]),
            "bollinger_upper": latest(bands["upper"]),
            "donchian_lower": latest(channels["lower"]), "donchian_upper": latest(channels["upper"]),
            "volume": round(volumes[-1], 6),
        },
        "series": {"ema_fast": fast, "ema_slow": slow, "rsi": rsi_values, "atr": atr_values},
        "disclaimer": "Research indicators only. Input candles are not authenticated as live; this endpoint never submits orders.",
    }


def _provider_key_present(*names: str) -> bool:
    return any(os.getenv(name, "").strip() for name in names)


@app.get("/v1/ai/status")
def ai_status(_: str = Depends(_device)) -> dict[str, Any]:
    providers = [
        ("gemini", ("GEMINI_API_KEY", "GOOGLE_API_KEY"), os.getenv("GEMINI_MODEL", "gemini")),
        ("openrouter", ("OPENROUTER_API_KEY",), os.getenv("OPENROUTER_MODEL", "configured-model")),
        ("openai", ("OPENAI_API_KEY",), os.getenv("OPENAI_MODEL", "configured-model")),
    ]
    selected = next((item for item in providers if _provider_key_present(*item[1])), None)
    return {
        "provider": selected[0] if selected else "deterministic_fallback",
        "model": selected[2] if selected else "five-layer-quant-context",
        "status": "configured" if selected else "fallback_ready",
        "llm_configured": selected is not None,
        "message": "Cloud model key detected; connectivity is tested separately." if selected else "No supported LLM key is configured. Chat can still report actual market fields and deterministic risk gates; it will not pretend an LLM answered.",
        "signal_only": True,
    }


@app.post("/v1/providers/ai/test")
def test_ai_providers(_: str = Depends(_device)) -> dict[str, Any]:
    checks = [
        {"provider": "gemini", "configured": _provider_key_present("GEMINI_API_KEY", "GOOGLE_API_KEY"), "ok": False},
        {"provider": "openrouter", "configured": _provider_key_present("OPENROUTER_API_KEY"), "ok": False},
        {"provider": "openai", "configured": _provider_key_present("OPENAI_API_KEY"), "ok": False},
    ]
    return {
        "status": "configured_not_connectivity_tested" if any(item["configured"] for item in checks) else "not_configured",
        "checks": checks,
        "message": "Credentials are present, but no provider response is marked OK until an actual authenticated model request is implemented and verified." if any(item["configured"] for item in checks) else "No cloud AI provider key is configured.",
    }


@app.post("/v1/providers/search/status")
def search_provider_status(_: str = Depends(_device)) -> dict[str, Any]:
    exa = _provider_key_present("EXA_API_KEY")
    tavily = _provider_key_present("TAVILY_API_KEY")
    return {
        "status": "configured" if exa or tavily else "not_configured",
        "providers": {
            "exa": {"configured": exa, "ok": False, "status": "configured_not_tested" if exa else "not_configured"},
            "tavily": {"configured": tavily, "ok": False, "status": "configured_not_tested" if tavily else "not_configured"},
        },
        "message": "Keys are present; use Search Test to verify an actual request." if exa or tavily else "Configure EXA_API_KEY and/or TAVILY_API_KEY on Railway.",
    }


@app.post("/v1/providers/search/test")
def test_search_providers(_: str = Depends(_device)) -> dict[str, Any]:
    exa = _provider_key_present("EXA_API_KEY")
    tavily = _provider_key_present("TAVILY_API_KEY")
    evidence = fetch_market_news_sentiment("NIFTY", exa_api_key=os.getenv("EXA_API_KEY"), tavily_api_key=os.getenv("TAVILY_API_KEY"))
    sources = list(evidence.get("sources") or [])
    articles = list(evidence.get("articles") or [])
    checks = [
        {"provider": "exa", "configured": exa, "ok": "exa" in sources},
        {"provider": "tavily", "configured": tavily, "ok": "tavily" in sources},
    ]
    return {
        "status": "ok" if any(item["ok"] for item in checks) else "failed_or_no_evidence",
        "checks": checks, "providers": {item["provider"]: item for item in checks},
        "evidence_count": len(articles), "search_evidence": articles[:8],
        "errors": evidence.get("errors", []),
        "message": "Search returned source-backed headlines." if articles else "No source-backed headlines returned; check provider status, key permissions and Railway outbound access.",
    }


@app.post("/v1/ai/chat")
def ai_chat(body: dict[str, Any], _: str = Depends(_device)) -> dict[str, Any]:
    """Honest deterministic fallback until an authenticated LLM adapter is available."""
    index = str(body.get("index") or "NIFTY").strip().upper()
    if index not in INDEXES:
        raise HTTPException(status_code=400, detail="Unsupported index.")
    question = str(body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="A question is required.")
    try:
        payload = _get_signals()
        market = dict((payload.get("market") or {}).get(index) or {})
        signal = dict((payload.get("signals") or {}).get(index) or {})
        news = dict(signal.get("news_sentiment") or cached_market_news_sentiment(index))
        validation = dict(signal.get("live_validation") or {})
        reasons = signal.get("reasons") or signal.get("reason") or []
        if not isinstance(reasons, list):
            reasons = [str(reasons)]
        answer = (
            f"{index} market context (deterministic backend fallback, not an LLM response): "
            f"LTP={market.get('ltp') if market.get('ltp') is not None else 'unavailable'}; "
            f"quote age={market.get('age_seconds') if market.get('age_seconds') is not None else 'unknown'} seconds; "
            f"signal={signal.get('decision', 'WAIT')}; validation={validation.get('verdict', 'NOT_AVAILABLE')}. "
            f"Reason: {'; '.join(str(item) for item in reasons[:5]) or 'No verified signal explanation returned'}. "
            "Missing/stale evidence blocks action. This API is signal-only and never places broker orders."
        )
        return {
            "answer": answer, "provider": "deterministic_fallback",
            "model": "five-layer-quant-context", "llm_used": False,
            "index": index, "question": question,
            "market": market, "signal": signal, "validation": validation,
            "search_evidence": news.get("articles", [])[:8],
            "status": "fallback_response", "signal_only": True,
        }
    except HTTPException as exc:
        raise HTTPException(status_code=503, detail={"message": "Current market context is unavailable.", "reason": str(exc.detail)[:180]}) from exc


@app.get("/v1/live/orders")
def live_orders(_: str = Depends(_device)) -> dict[str, Any]:
    return {
        "status": "read_only", "orders": [], "order_placement_enabled": False,
        "message": "This backend intentionally does not expose order placement or a live order book. Connect a read-only broker order-history adapter before displaying broker orders.",
    }


@app.get("/v1/portfolio")
def portfolio(_: str = Depends(_device)) -> dict[str, Any]:
    return {
        "status": "not_available", "positions": [], "holdings": [], "orders": [],
        "source": "angelone_smartapi", "read_only": True,
        "message": "The current adapter does not implement authenticated holdings/positions endpoints. No portfolio values are fabricated.",
    }


_paper_trades_memory: dict[str, dict[str, Any]] = {}


def _paper_trade_path() -> Path:
    return Path(os.getenv("PAPER_TRADES_FILE", "/data/paper_trades.json"))


def _load_paper_trades() -> list[dict[str, Any]]:
    with _lock:
        path = _paper_trade_path()
        try:
            if path.is_file():
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    _paper_trades_memory.clear()
                    for item in raw:
                        if isinstance(item, dict) and item.get("trade_id"):
                            _paper_trades_memory[str(item["trade_id"])] = dict(item)
        except (OSError, ValueError, TypeError):
            # Keep the last in-memory state if a mounted volume is temporarily unavailable.
            pass
        return [dict(item) for item in _paper_trades_memory.values()]


def _save_paper_trades(rows: list[dict[str, Any]]) -> bool:
    with _lock:
        _paper_trades_memory.clear()
        _paper_trades_memory.update({str(item["trade_id"]): dict(item) for item in rows if item.get("trade_id")})
        path = _paper_trade_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            temporary.replace(path)
            return True
        except OSError:
            # API remains honest about volatility; it never claims disk persistence.
            return False


@app.get("/v1/paper/trades")
def paper_trades(_: str = Depends(_device)) -> dict[str, Any]:
    rows = _load_paper_trades()
    rows.sort(key=lambda item: str(item.get("opened_at") or ""), reverse=True)
    return {
        "status": "ok", "trades": rows, "trade_count": len(rows),
        "persistence": "persistent" if _paper_trade_path().is_file() else "memory_or_empty",
        "signal_only": True, "order_placement_enabled": False,
    }


@app.post("/v1/paper/trades/open")
def open_paper_trade(body: dict[str, Any], _: str = Depends(_device)) -> dict[str, Any]:
    trade_id = str(body.get("trade_id") or "").strip()
    index = str(body.get("index") or "").strip().upper()
    side = str(body.get("side") or "").strip().upper()
    if not trade_id or len(trade_id) > 128:
        raise HTTPException(status_code=422, detail="trade_id is required and must be at most 128 characters.")
    if index not in INDEXES:
        raise HTTPException(status_code=422, detail="Unsupported index.")
    if side not in {"CALL", "PUT", "CALL BUY", "PUT BUY", "LONG", "SHORT"}:
        raise HTTPException(status_code=422, detail="Unsupported paper-trade side.")
    slippage_r = _number(body.get("slippage_r"))
    transaction_cost_r = _number(body.get("transaction_cost_r"))
    slippage_r = 0.02 if slippage_r is None else slippage_r
    transaction_cost_r = 0.02 if transaction_cost_r is None else transaction_cost_r
    if not 0 <= slippage_r <= 1 or not 0 <= transaction_cost_r <= 1:
        raise HTTPException(status_code=422, detail="Paper slippage and transaction costs must be between 0 and 1 R.")
    rows = _load_paper_trades()
    if any(str(item.get("trade_id")) == trade_id for item in rows):
        raise HTTPException(status_code=409, detail="A paper trade with this trade_id already exists.")
    trade = {
        "trade_id": trade_id, "strategy_id": str(body.get("strategy_id") or "manual-paper")[:128],
        "index": index, "side": side, "regime": str(body.get("regime") or "UNVERIFIED")[:64],
        "status": "OPEN", "slippage_r": slippage_r, "transaction_cost_r": transaction_cost_r,
        "gross_r": None, "net_r": None, "notes": str(body.get("notes") or "")[:1000],
        "opened_at": _utc_now().isoformat(), "closed_at": None, "paper_only": True,
    }
    rows.append(trade)
    persisted = _save_paper_trades(rows)
    return {
        "status": "ok", "trade": trade, "persistence": "persistent" if persisted else "memory_only",
        "message": "Paper trade recorded; no broker order was submitted.",
    }


@app.post("/v1/paper/trades/{trade_id}/close")
def close_paper_trade(trade_id: str, body: dict[str, Any], _: str = Depends(_device)) -> dict[str, Any]:
    gross_r = _number(body.get("gross_r"))
    if gross_r is None:
        raise HTTPException(status_code=422, detail="gross_r must be a finite number.")
    rows = _load_paper_trades()
    trade = next((item for item in rows if str(item.get("trade_id")) == trade_id), None)
    if trade is None:
        raise HTTPException(status_code=404, detail="Paper trade not found.")
    if trade.get("status") == "CLOSED":
        raise HTTPException(status_code=409, detail="Paper trade is already closed.")
    net_r = gross_r - float(trade.get("slippage_r") or 0) - float(trade.get("transaction_cost_r") or 0)
    trade.update({
        "status": "CLOSED", "gross_r": round(gross_r, 6), "net_r": round(net_r, 6),
        "closed_at": _utc_now().isoformat(),
        "notes": (str(trade.get("notes") or "") + (" | " if trade.get("notes") and body.get("notes") else "") + str(body.get("notes") or ""))[:1500],
    })
    persisted = _save_paper_trades(rows)
    return {
        "status": "ok", "trade": trade, "persistence": "persistent" if persisted else "memory_only",
        "message": "Paper result recorded after deducting the configured R-costs; no broker order was submitted.",
    }


@app.get("/v1/paper/report")
def paper_report(_: str = Depends(_device)) -> dict[str, Any]:
    rows = _load_paper_trades()
    closed = [item for item in rows if item.get("status") == "CLOSED" and _number(item.get("net_r")) is not None]
    values = [float(item["net_r"]) for item in closed]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    metrics = {
        "trade_count": len(closed),
        "win_rate": len(wins) / len(closed) if closed else None,
        "expectancy_r": round(sum(values) / len(values), 6) if values else None,
        "net_total_r": round(sum(values), 6),
        "profit_factor": round(sum(wins) / abs(sum(losses)), 6) if losses else (None if not wins else None),
        "open_trade_count": sum(1 for item in rows if item.get("status") == "OPEN"),
        "total_slippage_r": round(sum(float(item.get("slippage_r") or 0) for item in closed), 6),
        "total_transaction_cost_r": round(sum(float(item.get("transaction_cost_r") or 0) for item in closed), 6),
    }
    return {
        "status": "ok", "trade_count": len(closed), "metrics": metrics,
        "trades": closed, "mode": "PAPER_ONLY",
        "message": "Metrics are computed only from recorded closed paper trades; they are not a forecast or live P&L.",
    }


@app.get("/v1/signals")
def signals(ema_fast: int = Query(default=8, ge=2, le=50), ema_slow: int = Query(default=13, ge=3, le=100), _: str = Depends(_device)) -> dict[str, Any]:
    if ema_fast >= ema_slow:
        raise HTTPException(status_code=400, detail="ema_fast must be less than ema_slow")
    try:
        return _get_signals()
    except HTTPException as exc:
        if exc.status_code in (503, 502):
            # The app still receives explicit WAIT rows and a clear feed error.
            return _empty_payload(str(exc.detail))
        raise


@app.post("/v1/backtest/historical")
def historical_backtest(body: BacktestRequest, _: str = Depends(_device)) -> dict[str, Any]:
    adapter = _require_adapter()
    index = body.index.strip().upper()
    if body.symboltoken:
        exchange = (body.exchange or "NSE").strip().upper()
        token = body.symboltoken.strip()
    else:
        config = INDEXES.get(index)
        if config is None:
            raise HTTPException(status_code=400, detail=f"Unsupported index: {index}")
        exchange = (body.exchange or config["exchange"]).strip().upper()
        token = config["token"]

    start_value = body.from_date or body.fromdate
    end_value = body.to_date or body.todate
    if not start_value or not end_value:
        raise HTTPException(status_code=422, detail="from_date and to_date are required.")
    def bound(value: str, end: bool) -> str:
        text = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return f"{text} {'15:30' if end else '09:15'}"
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(IST)
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=422, detail="Dates must use YYYY-MM-DD or YYYY-MM-DD HH:MM.")
    start_text, end_text = bound(start_value, False), bound(end_value, True)
    start_dt = datetime.strptime(start_text, "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    end_dt = datetime.strptime(end_text, "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    if end_dt <= start_dt or end_dt - start_dt > timedelta(days=31):
        raise HTTPException(status_code=422, detail="Choose a valid historical range of 31 days or less.")
    if body.fast_ema >= body.slow_ema:
        raise HTTPException(status_code=422, detail="fast_ema must be less than slow_ema.")
    if body.interval not in {"ONE_MINUTE", "FIVE_MINUTE", "FIFTEEN_MINUTE", "ONE_HOUR"}:
        raise HTTPException(status_code=422, detail="Unsupported candle interval.")

    try:
        candles = adapter.candles(exchange, token, body.interval, start_text, end_text).get("candles") or []
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Angel One historical candle request failed; no synthetic backtest data was used.") from exc
    valid_rows = [
        row for row in candles
        if isinstance(row, (list, tuple)) and len(row) >= 6
        and _number(row[1]) is not None and _number(row[2]) is not None
        and _number(row[3]) is not None and _number(row[4]) is not None
    ]
    valid_rows.sort(key=lambda row: str(row[0]))
    closes = [_number(row[4]) for row in valid_rows]
    closes = [value for value in closes if value is not None]
    required = max(body.slow_ema + 2, body.atr_period + 2)
    if len(valid_rows) < required or len(closes) != len(valid_rows):
        raise HTTPException(status_code=422, detail=f"At least {required} valid historical candles are required for these EMA/ATR settings.")

    fast_line = _ema_series(closes, body.fast_ema)
    slow_line = _ema_series(closes, body.slow_ema)
    true_ranges: list[float] = []
    previous_close: float | None = None
    for row in valid_rows:
        high, low, close = float(row[2]), float(row[3]), float(row[4])
        tr = max(high - low, abs(high - previous_close), abs(low - previous_close)) if previous_close is not None else high - low
        true_ranges.append(tr)
        previous_close = close
    atr_values: list[float | None] = []
    for i in range(len(true_ranges)):
        atr_values.append(sum(true_ranges[i - body.atr_period + 1:i + 1]) / body.atr_period if i + 1 >= body.atr_period else None)

    trades: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None
    equity = body.initial_capital
    equity_curve_r = 0.0
    peak_r = 0.0
    max_drawdown_r = 0.0

    def close_position(exit_index: int, exit_price: float, reason: str) -> None:
        nonlocal position, equity, equity_curve_r, peak_r, max_drawdown_r
        if position is None:
            return
        risk_distance = float(position["risk_distance"])
        gross_r = (exit_price - float(position["entry_price"])) / risk_distance
        net_r = gross_r - body.slippage_r - body.transaction_cost_r
        units = position_size(equity, 0.01, float(position["entry_price"]), float(position["stop_loss"]), lot_size=1)
        pnl = net_r * risk_distance * units
        equity += pnl
        equity_curve_r += net_r
        peak_r = max(peak_r, equity_curve_r)
        max_drawdown_r = max(max_drawdown_r, peak_r - equity_curve_r)
        trades.append({
            "side": "LONG",
            "entry_time": str(valid_rows[position["entry_index"]][0]),
            "exit_time": str(valid_rows[exit_index][0]),
            "entry_price": round(float(position["entry_price"]), 4),
            "exit_price": round(float(exit_price), 4),
            "stop_loss": round(float(position["stop_loss"]), 4),
            "target": round(float(position["target"]), 4),
            "gross_r": round(gross_r, 4), "net_r": round(net_r, 4),
            "r": round(net_r, 4), "pnl": round(pnl, 2),
            "bars_held": max(1, exit_index - position["entry_index"] + 1),
            "units": units, "risk_budget_fraction": 0.01,
            "exit_reason": reason,
        })
        position = None

    start_index = max(body.slow_ema, body.atr_period)
    for i in range(start_index, len(valid_rows) - 1):
        row = valid_rows[i]
        open_price, high, low, close = float(row[1]), float(row[2]), float(row[3]), float(row[4])
        if position is not None and i >= position["entry_index"]:
            # Conservative same-bar handling: if stop and target are both touched,
            # assume the stop was hit first because candle sequencing is unknown.
            stop_hit = low <= float(position["stop_loss"])
            target_hit = high >= float(position["target"])
            if stop_hit:
                close_position(i, float(position["stop_loss"]), "STOP_LOSS" if not target_hit else "STOP_FIRST_BOTH_TOUCHED")
                continue
            if target_hit:
                close_position(i, float(position["target"]), "TARGET")
                continue
            if i - position["entry_index"] + 1 >= body.max_hold_bars:
                close_position(i + 1, float(valid_rows[i + 1][1]), "MAX_HOLD")
                continue
            crossed_down = fast_line[i] < slow_line[i] and fast_line[i - 1] >= slow_line[i - 1]
            if crossed_down:
                close_position(i + 1, float(valid_rows[i + 1][1]), "EMA_CROSS_EXIT")
                continue
        if position is None:
            crossed_up = fast_line[i] > slow_line[i] and fast_line[i - 1] <= slow_line[i - 1]
            atr = atr_values[i]
            if crossed_up and atr is not None and atr > 0:
                entry_index = i + 1
                entry_price = float(valid_rows[entry_index][1])
                risk_distance = atr * body.stop_atr
                position = {
                    "entry_index": entry_index, "entry_price": entry_price,
                    "risk_distance": risk_distance,
                    "stop_loss": entry_price - risk_distance,
                    "target": entry_price + risk_distance * body.target_r,
                }
    if position is not None:
        last_index = len(valid_rows) - 1
        close_position(last_index, float(valid_rows[last_index][4]), "END_OF_DATA")

    net_rs = [float(trade["net_r"]) for trade in trades]
    wins = [value for value in net_rs if value > 0]
    losses = [value for value in net_rs if value < 0]
    metrics = {
        "n": len(trades),
        "win_rate": len(wins) / len(trades) if trades else None,
        "expectancy_r": round(sum(net_rs) / len(net_rs), 4) if trades else None,
        "net_total_r": round(sum(net_rs), 4),
        "profit_factor": round(sum(wins) / abs(sum(losses)), 4) if losses else (None if not wins else None),
        "max_drawdown_r": round(max_drawdown_r, 4),
        "ending_equity": round(equity, 2),
        "return_pct": round((equity / body.initial_capital - 1.0) * 100.0, 3),
    }
    report = {
        "status": "OK" if trades else "NO_TRADES",
        "mode": "ANGELONE_HISTORICAL_EMA_ATR",
        "candle_count": len(valid_rows),
        "first_candle": str(valid_rows[0][0]),
        "last_candle": str(valid_rows[-1][0]),
        "metrics": metrics,
        "trades": trades,
        "assumptions": [
            f"EMA {body.fast_ema}/{body.slow_ema} crossover; ATR({body.atr_period}) stop = {body.stop_atr}x ATR; target = {body.target_r}R",
            "Signal is evaluated on a candle close and fills on the next candle open; intrabar stop/target collisions assume stop first.",
            f"Position sizing risks 1% of current equity per trade; costs subtract {body.slippage_r}R slippage and {body.transaction_cost_r}R transaction cost per round trip.",
            "Long-only underlying-index research baseline; not an options premium backtest and not a profit guarantee.",
            "Excludes taxes, brokerage-specific charges, latency, margin, partial fills and real order-book execution.",
        ],
    }
    return {"status": "ok", "source": "angelone_smartapi_historical_candles", "index": index, "exchange": exchange, "symboltoken": token, "interval": body.interval, "report": report}
