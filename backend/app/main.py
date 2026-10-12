"""AI-TRADING read-only live market API.

Signals fail closed: absent credentials, stale source timestamps, incomplete
option depth/Greeks, conflicting timeframes, or missing option ATR means WAIT.
This service never places, modifies, or cancels broker orders.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import time
import urllib.request
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.angelone_readonly import AngelOneConfigError, AngelOneReadOnly
from integrations.angelone_stream import AngelOneStream, EXCHANGE_TYPES
from integrations.news_sentiment import fetch_market_news_sentiment
from quant_engine import evaluate_five_layer_signal, evaluate_futures_signal

app = FastAPI(title="AI-TRADING Read-only Signals API", version="1.0.0")
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
    fast_line = _ema_series(closes, 8)
    slow_line = _ema_series(closes, 21)
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes[-15:-1], closes[-14:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / len(gains) if gains else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    rsi = 100.0 if avg_loss == 0 and avg_gain > 0 else 50.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
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
    return {
        "ema_fast_8": fast_line[-1],
        "ema_slow_21": slow_line[-1],
        "ema_alignment": "BULLISH" if fast_line[-1] > slow_line[-1] else "BEARISH" if fast_line[-1] < slow_line[-1] else "NEUTRAL",
        "rsi_14": round(rsi, 2),
        "macd_line": round(macd_line[-1], 4) if macd_line else None,
        "macd_signal": round(macd_signal[-1], 4) if macd_signal else None,
        "macd_histogram": round(macd_histogram, 4) if macd_histogram is not None else None,
        "underlying_atr_14": _atr_from_candles(candle_rows, 14),
        "vwap": vwap_numerator / vwap_denominator if vwap_denominator > 0 else None,
        "vwap_source": "session OHLCV" if vwap_denominator > 0 else "UNAVAILABLE_NO_VOLUME",
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
    sentiment = max(-1.0, min(1.0, sum(sentiment_components.values())))
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
        "sentiment_source": "session price structure and order-book depth; news sentiment not configured",
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
    market = {
        "ltp": spot, "age_seconds": result.get("layers", {}).get("data_quality", {}).get("age_seconds"),
        "feed_mode": spot_quote.get("_source_mode", "REST_FULL_DEPTH"), "source": "angelone_smartapi",
        "source_timestamp": spot_ts, "timestamp": spot_ts,
        "live": result.get("data_fresh") is True, "day_move_pct": round(day_move * 100, 3),
        "sentiment_score": sentiment, "sentiment_label": "BULLISH" if sentiment >= 0.2 else "BEARISH" if sentiment <= -0.2 else "NEUTRAL",
        "sentiment_source": "intraday OHLC + multi-timeframe trend + option OI PCR + top-five bid/ask depth",
        "sentiment_components": sentiment_components, "pcr": pcr,
        "session_open": day_open, "session_high": day_high, "session_low": day_low,
        "session_range_position": round(day_range_position, 4),
        "depth_imbalance": round(depth_imbalance, 4),
        "indicators": indicators,
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
            # Never echo SDK request/response details from a credential-bearing login.
            raise HTTPException(status_code=502, detail="Angel One login failed. Verify API key, Client ID, MPIN, current TOTP and SmartAPI access.") from exc
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
        signals: dict[str, Any] = {}
        market: dict[str, Any] = {}
        for index in INDEXES:
            try:
                result, quote = _index_snapshot(adapter, rows, index)
                signals[index] = result
                market[index] = quote
            except Exception as exc:
                signals[index] = _wait_signal(index, str(exc)[:220])
                market[index] = {"ltp": None, "age_seconds": None, "feed_mode": "DATA_ERROR", "source": "angelone_smartapi", "error": str(exc)[:160]}
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
        risk_cash = equity * 0.01
        pnl = net_r * risk_cash
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

