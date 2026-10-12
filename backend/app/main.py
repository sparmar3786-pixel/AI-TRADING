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
from quant_engine import evaluate_five_layer_signal

app = FastAPI(title="AI-TRADING Read-only Signals API", version="1.0.0")
IST = ZoneInfo("Asia/Kolkata")
MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
MASTER_TTL_SECONDS = 6 * 60 * 60
SIGNAL_CACHE_SECONDS = 12
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
_saved_meta: dict[str, Any] = {}
_master_rows: list[dict[str, Any]] = []
_master_loaded_at = 0.0
_signal_cache: dict[str, Any] | None = None
_signal_cache_at = 0.0
_confirmation_states: dict[str, dict[str, Any]] = {}
_last_market: dict[str, Any] = {}


class ConnectRequest(BaseModel):
    angel_api_key: str | None = Field(default=None, max_length=256)
    angel_client_code: str | None = Field(default=None, max_length=128)
    angel_pin: str | None = Field(default=None, max_length=128)
    angel_totp: str | None = Field(default=None, max_length=128)
    remember_credentials: bool = True


class BacktestRequest(BaseModel):
    exchange: str = "NSE"
    symboltoken: str = Field(min_length=1, max_length=32)
    interval: str = "FIVE_MINUTE"
    fromdate: str
    todate: str
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
                except Exception:
                    _adapter = None
        return _adapter


def _require_adapter() -> AngelOneReadOnly:
    adapter = _current_adapter(attempt_env_login=True)
    if adapter is None:
        raise HTTPException(status_code=503, detail="Angel One is not connected. Open API & Railway and connect with API key, Client ID, MPIN and current TOTP.")
    try:
        adapter.profile()
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
    result = adapter.market_data("FULL", {exchange: list(dict.fromkeys(tokens))})
    output: dict[str, dict[str, Any]] = {}
    for row in _quote_rows(result):
        token = str(row.get("symbolToken") or row.get("symboltoken") or row.get("token") or "")
        if token:
            output[token] = row
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


def _greeks_map(adapter: AngelOneReadOnly, name: str, expiry: str) -> dict[tuple[float, str], float]:
    try:
        data = adapter.option_greeks(name, expiry).get("data") or []
    except Exception:
        return {}
    mapped: dict[tuple[float, str], float] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        strike = _number(row.get("strikePrice") or row.get("strike"))
        if strike is None:
            continue
        kind = str(row.get("optionType") or row.get("optiontype") or "").upper()
        kind = "CALL" if kind in ("CE", "CALL") else "PUT" if kind in ("PE", "PUT") else ""
        delta = _number(row.get("delta"))
        if kind and delta is not None:
            mapped[(strike, kind)] = delta
    return mapped


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
    day_open = _number(candle_rows[0][1]) if candle_rows and isinstance(candle_rows[0], (list, tuple)) and len(candle_rows[0]) > 1 else closes[0]
    day_move = (spot - day_open) / day_open if day_open else 0.0
    up_count = sum(1 for tf in timeframe_closes.values() if len(tf) >= 3 and tf[-1] > tf[-2] > tf[-3])
    down_count = sum(1 for tf in timeframe_closes.values() if len(tf) >= 3 and tf[-1] < tf[-2] < tf[-3])
    sentiment = max(-1.0, min(1.0, (0.25 if day_move > 0 else -0.25 if day_move < 0 else 0.0) + (0.25 if up_count >= 2 else -0.25 if down_count >= 2 else 0.0)))
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
    wanted_strikes = set(strike_values[max(0, atm_index - 3): min(len(strike_values), atm_index + 4)])
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
        delta = greeks.get((strike or -1, kind or ""))
        timestamp = _quote_timestamp(quote)
        if timestamp:
            quote_time_by_token[token] = timestamp
        normalized_options.append({
            "token": token, "exchange": exchange, "option_type": kind,
            "strike": strike, "expiry": selected_expiry.isoformat(),
            "symbol": str(row.get("symbol", "")), "bid": obid, "ask": oask,
            "ltp": ltp, "volume": volume, "oi": oi, "delta": delta,
            "timestamp": timestamp,
        })
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
        "order_flow": {"bid": bid, "ask": ask, "ltp": spot, "buy_volume": buy_volume, "sell_volume": sell_volume},
        "option_chain": [
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
    result.update({
        "index": index, "data_source": "angelone_smartapi",
        "data_fresh": result.get("layers", {}).get("data_quality", {}).get("pass") is True,
        "sentiment_source": "session price structure and order-book depth; news sentiment not configured",
        "day_move_pct": round(day_move * 100, 3),
        "indicator_summary": {"timeframes": timeframe_closes, "five_minute_trend": trend},
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
    market = {
        "ltp": spot, "age_seconds": result.get("layers", {}).get("data_quality", {}).get("age_seconds"),
        "feed_mode": "REST_FULL_DEPTH", "source": "angelone_smartapi",
        "source_timestamp": spot_ts, "day_move_pct": round(day_move * 100, 3),
        "sentiment_score": sentiment, "sentiment_label": "BULLISH" if sentiment >= 0.2 else "BEARISH" if sentiment <= -0.2 else "NEUTRAL",
    }
    return result, market


def _empty_payload(reason: str) -> dict[str, Any]:
    now = _utc_now().isoformat()
    return {
        "live": False, "last_fetch": None,
        "feed": {"authenticated": False, "connected": False, "mode": "REST_FULL_DEPTH", "message": reason},
        "store": {"source": "angelone_smartapi", "fresh": False, "message": reason},
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
    return {
        **status,
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
        "angel_totp_secret": (body.angel_totp or "").strip(),
    }
    with _lock:
        if not all(supplied.values()):
            if _adapter and _adapter.authenticated:
                return {**_adapter.status(), "session_restored": True, "stored_session": True, "login_message": "Existing in-memory session is authenticated"}
            saved = _load_credentials()
            env = _credentials_from_env()
            base = {**saved, **env}
            if not all(base.get(key) for key in ("angel_api_key", "angel_client_code", "angel_pin")) or not supplied["angel_totp_secret"]:
                raise HTTPException(status_code=422, detail="Enter API key, Client ID, MPIN and current TOTP for a fresh Angel One login.")
            supplied.update(base)
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
            # SDK errors can include sensitive broker data; return only a safe class/message.
            safe = str(exc).splitlines()[0][:180]
            raise HTTPException(status_code=502, detail=f"Angel One login failed: {safe}") from exc
        status = adapter.status()
        if not status["has_jwt_token"] or not status["has_feed_token"]:
            raise HTTPException(status_code=502, detail="Profile login succeeded but JWT/feed token readiness was not verified. Check SmartAPI SDK version/session response.")
        if body.remember_credentials:
            _save_credentials(supplied)
        _adapter = adapter
        _signal_cache = None
        _signal_cache_at = 0.0
        return {
            **status, "authenticated": True, "session_restored": False,
            "stored_session": True, "stored_credentials": body.remember_credentials,
            "login_message": "Angel One authenticated; JWT and feed token verified. No order-placement API is enabled.",
            "profile": {"client_code": profile.get("client_code"), "name": profile.get("name")},
        }


@app.get("/v1/system/diagnostics")
def diagnostics(_: str = Depends(_device)) -> dict[str, Any]:
    adapter = _current_adapter()
    return {
        "service": "ai-trading-readonly-api",
        "angel": adapter.status() if adapter else {"authenticated": False, "has_jwt_token": False, "has_feed_token": False},
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
    # Do not claim a WebSocket is active: this backend currently polls SmartAPI REST.
    requested = [str(item).upper() for item in body.get("indexes", []) if str(item).upper() in INDEXES]
    return {
        "started": False, "mode": "REST_POLLING",
        "indexes": requested, "authenticated": bool((_current_adapter() or AngelOneReadOnly()).authenticated),
        "message": "WebSocket streaming is not enabled in this release; live data uses timestamp-validated REST FULL-depth snapshots.",
    }


@app.get("/v1/live/status")
def live_status(_: str = Depends(_device)) -> dict[str, Any]:
    adapter = _current_adapter()
    connected = bool(adapter and adapter.authenticated)
    return {
        "authenticated": connected, "live": bool(_signal_cache and _signal_cache.get("live")),
        "feed_mode": "REST_FULL_DEPTH" if connected else "NO_FEED",
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
            "delta": greek_map.get((strike or -1, kind or "")),
            "buy_depth": buy_depth, "sell_depth": sell_depth,
            "source_timestamp": _quote_timestamp(quote),
        })
    return {"index": index, "spot": spot, "expiry": expiries[0].isoformat(), "contracts": output, "source": "angelone_smartapi", "observed_at": _utc_now().isoformat(), "signal_only": True}


@app.get("/v1/market/sentiment")
def market_sentiment(index: str = Query(default="NIFTY"), _: str = Depends(_device)) -> dict[str, Any]:
    payload = _get_signals(force=False)
    key = index.strip().upper()
    if key not in INDEXES:
        raise HTTPException(status_code=400, detail=f"Unsupported index. Choose from {', '.join(INDEXES)}.")
    signal = payload["signals"].get(key, {})
    market = payload["market"].get(key, {})
    return {
        "index": key, "sentiment": market.get("sentiment_label", "UNKNOWN"),
        "score": market.get("sentiment_score"), "day_move_pct": market.get("day_move_pct"),
        "trend": (signal.get("indicator_summary") or {}).get("five_minute_trend", "UNKNOWN"),
        "source": "session price structure and order-book depth",
        "news_sentiment": "NOT_CONFIGURED", "observed_at": payload.get("last_fetch"),
    }


def _get_signals(force: bool = False) -> dict[str, Any]:
    global _signal_cache, _signal_cache_at, _last_market
    with _lock:
        if _signal_cache is not None and not force and time.monotonic() - _signal_cache_at < SIGNAL_CACHE_SECONDS:
            return _signal_cache
    adapter = _require_adapter()
    try:
        rows = _load_master()
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
            "feed": {"authenticated": True, "connected": live, "mode": "REST_FULL_DEPTH", "message": "Fresh exchange-timestamped market data" if live else "Connected but no index passed freshness/data gates"},
            "store": {"source": "angelone_smartapi", "fresh": live, "index_count": len(signals)},
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
    # Only active MCX futures with a valid expiry are surfaced; never use demo quotes.
    today = datetime.now(IST).date()
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
            result.append({"symbol": name, "status": "WAIT", "reason": "No active MCX futures contract in instrument master", "ltp": None})
            continue
        contract = contracts[0]
        try:
            quote = _quotes(adapter, "MCX", [str(contract["token"])]).get(str(contract["token"]), {})
            ltp = _number(quote.get("ltp"))
            timestamp = _quote_timestamp(quote)
            result.append({
                "symbol": name, "status": "LIVE" if ltp and timestamp else "WAIT",
                "contract": contract.get("symbol"), "expiry": _expiry_date(contract.get("expiry")).isoformat(),
                "ltp": ltp, "source_timestamp": timestamp, "source": "angelone_smartapi",
                "reason": None if ltp and timestamp else "Quote lacks a fresh price or exchange timestamp",
            })
        except Exception as exc:
            result.append({"symbol": name, "status": "WAIT", "reason": str(exc)[:160], "ltp": None})
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
    try:
        candles = adapter.candles(body.exchange, body.symboltoken, body.interval, body.fromdate, body.todate).get("candles") or []
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Angel One historical candle request failed; no synthetic backtest data was used.") from exc
    closes = _candle_closes(candles)
    if len(closes) < 30:
        raise HTTPException(status_code=422, detail="At least 30 valid historical closes are required for backtesting.")
    fast, slow = 8, 21
    def ema(values: list[float], period: int) -> list[float]:
        alpha = 2 / (period + 1)
        output = [values[0]]
        for value in values[1:]:
            output.append(alpha * value + (1 - alpha) * output[-1])
        return output
    fast_line, slow_line = ema(closes, fast), ema(closes, slow)
    position = 0
    trades = []
    equity = body.initial_capital
    for i in range(1, len(closes) - 1):
        desired = 1 if fast_line[i] > slow_line[i] else 0
        if desired != position:
            # Execute on the next bar close, never on the same bar as the signal.
            fill = closes[i + 1]
            if position:
                pnl = (fill - entry_price) / entry_price * equity
                equity += pnl
                trades.append({"side": "EXIT_LONG", "bar": i + 1, "price": fill, "pnl": round(pnl, 2)})
            elif desired:
                entry_price = fill
                trades.append({"side": "ENTER_LONG", "bar": i + 1, "price": fill, "pnl": 0.0})
            position = desired
    return {
        "status": "ok", "source": "angelone_smartapi_historical_candles",
        "exchange": body.exchange, "symboltoken": body.symboltoken, "interval": body.interval,
        "bars": len(closes), "initial_capital": body.initial_capital, "ending_equity": round(equity, 2),
        "return_pct": round((equity / body.initial_capital - 1) * 100, 3),
        "trades": trades, "trade_count": len(trades),
        "limitations": ["Long-only EMA 8/21 research baseline", "next-bar-close fills", "excludes option premium, taxes, spread, brokerage, margin and slippage", "not a profit guarantee"],
    }
