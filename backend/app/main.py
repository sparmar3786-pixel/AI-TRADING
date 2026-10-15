"""AI-TRADING read-only live market API.

Signals fail closed: absent credentials, stale source timestamps, incomplete
option depth/Greeks, conflicting timeframes, or missing option ATR means WAIT.
This service never places, modifies, or cancels broker orders.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import asyncio
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
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
from strategies.suite import evaluate_strategy_suite
try:
    # Docker image runs the service as app.main with backend/app copied to /app/app.
    from app.smc_api import router as smc_router
except ModuleNotFoundError:
    # Repository unit tests import backend.app.main from the repository root.
    from backend.app.smc_api import router as smc_router
from risk.position_sizing import position_size

try:
    from app.kumo_nim_api import router as kumo_router
except ModuleNotFoundError:
    from backend.app.kumo_nim_api import router as kumo_router

app = FastAPI(title="AI-TRADING Read-only Signals API", version="1.0.0")
app.include_router(smc_router)
app.include_router(kumo_router)
try:
    from app.realtime_chart import router as realtime_chart_router
except ModuleNotFoundError:
    from backend.app.realtime_chart import router as realtime_chart_router
app.include_router(realtime_chart_router)
try:
    from integrations.chart_bridge import publish_angelone_tick
except ImportError:
    publish_angelone_tick = None
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
COMMODITY_NAMES = ("CRUDEOIL", "CRUDEOILM", "NATURALGAS", "NATGASMINI", "GOLD", "GOLDM", "SILVER", "SILVERM", "COPPER", "ZINC", "ALUMINIUM", "LEAD", "NICKEL", "MENTHAOIL", "CASTORSEED", "COTTON", "RUBBER")
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
_market_data_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="market-data")
# A short cache absorbs aggressive mobile polling without masking market moves.
# Signal gates independently enforce freshness and never treat cache age as a live tick.
OPTION_CHAIN_CACHE_TTL_SECONDS = max(0.0, min(float(os.getenv("OPTION_CHAIN_CACHE_TTL_SECONDS", "2.0")), 5.0))
OPTION_CHAIN_UPSTREAM_TIMEOUT_SECONDS = max(1.0, min(float(os.getenv("OPTION_CHAIN_UPSTREAM_TIMEOUT_SECONDS", "4.0")), 10.0))
_option_chain_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_signal_cache: dict[str, Any] | None = None
_signal_cache_at = 0.0
# Signal computation is refreshed in the background so a cold/slow broker
# cycle cannot make every HTTP client wait for the full multi-index fan-out.
_signal_build_lock = threading.Lock()
_signal_build_metrics: dict[str, Any] = {"last_duration_ms": None, "build_count": 0, "in_flight": False, "last_error": None}
_request_metrics: dict[str, dict[str, Any]] = {}
_ai_provider_test_cache: dict[str, dict[str, Any]] = {}
_confirmation_states: dict[str, dict[str, Any]] = {}
_last_market: dict[str, Any] = {}
_option_history: dict[str, dict[str, float]] = {}
# Retain only real broker candles/depth observed since this process started,
# so a WebSocket reconnect does not erase captured footprint levels.
_footprint_history: dict[str, list[dict[str, Any]]] = {}
_footprint_history_interval: dict[str, str] = {}

def _record_request_metric(path: str, status_code: int, elapsed_ms: float, response_bytes: int | None) -> None:
    with _lock:
        item = dict(_request_metrics.get(path) or {"count": 0, "errors": 0, "total_ms": 0.0})
        item["count"] = int(item.get("count", 0)) + 1
        item["errors"] = int(item.get("errors", 0)) + (1 if status_code >= 400 else 0)
        item["total_ms"] = float(item.get("total_ms", 0.0)) + elapsed_ms
        item["last_ms"] = round(elapsed_ms, 1)
        item["average_ms"] = round(float(item["total_ms"]) / int(item["count"]), 1)
        item["last_status"] = int(status_code)
        item["last_response_bytes"] = response_bytes
        item["last_server_throughput_bytes_per_second"] = round(response_bytes / (elapsed_ms / 1000.0), 1) if response_bytes is not None and elapsed_ms > 0 else None
        _request_metrics[path] = item
        # Keep a bounded per-route table instead of growing forever.
        if len(_request_metrics) > 60:
            oldest = next(iter(_request_metrics))
            if oldest != path:
                _request_metrics.pop(oldest, None)

@app.middleware("http")
async def request_timing_middleware(request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _record_request_metric(request.url.path, 500, elapsed_ms, None)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        response_bytes = int(response.headers.get("content-length")) if response.headers.get("content-length") else None
    except (TypeError, ValueError):
        response_bytes = None
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    _record_request_metric(request.url.path, response.status_code, elapsed_ms, response_bytes)
    return response


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

def _is_market_session_open(symbol: str, now: datetime | None = None) -> bool:
    """Conservative weekday session clock; quote freshness remains an independent required gate."""
    local = (now or datetime.now(IST)).astimezone(IST)
    if local.weekday() >= 5:
        return False
    clock = local.time().replace(tzinfo=None)
    key = symbol.strip().upper()
    if key in COMMODITY_NAMES:
        return dt_time(9, 0) <= clock <= dt_time(23, 30)
    return dt_time(9, 15) <= clock <= dt_time(15, 30)


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


# Market intelligence is refreshed by the backend, not by opening the chat page.
MARKET_INTELLIGENCE_REFRESH_SECONDS = 900
_market_intel_lock = threading.Lock()
_market_intel_thread: threading.Thread | None = None
_market_intel_refreshing = False
_market_intel_state: dict[str, Any] = {
    "status": "PENDING",
    "summary": None,
    "articles": [],
    "market_context": {},
    "provider_checks": {},
    "updated_at": None,
    "next_refresh_at": None,
    "refresh_interval_seconds": MARKET_INTELLIGENCE_REFRESH_SECONDS,
    "summary_provider": None,
    "summary_model": None,
    "error": None,
}


def _refresh_market_intelligence_once() -> None:
    global _market_intel_refreshing, _market_intel_state
    with _market_intel_lock:
        if _market_intel_refreshing:
            return
        _market_intel_refreshing = True
        _market_intel_state = {**_market_intel_state, "status": "REFRESHING", "error": None}
    observed_at = _utc_now().isoformat()
    try:
        all_articles: list[dict[str, Any]] = []
        provider_checks: dict[str, Any] = {}
        index_news: dict[str, Any] = {}
        news_symbols = [*INDEXES.keys(), "MCX"]
        for index in news_symbols:
            evidence = fetch_market_news_sentiment(
                index,
                exa_api_key=os.getenv("EXA_API_KEY"),
                tavily_api_key=os.getenv("TAVILY_API_KEY"),
                force=True,
            )
            index_news[index] = {
                "status": evidence.get("status"),
                "label": evidence.get("label"),
                "score": evidence.get("score"),
                "article_count": evidence.get("article_count", 0),
                "sources": evidence.get("sources", []),
                "observed_at": evidence.get("observed_at"),
            }
            for provider, check in (evidence.get("provider_checks") or {}).items():
                provider_checks.setdefault(provider, {"configured": False, "ok": True, "result_count": 0, "indexes_checked": 0})
                current = provider_checks[provider]
                configured_for_index = check.get("configured") is True
                current["configured"] = current["configured"] or configured_for_index
                current["ok"] = current["ok"] and configured_for_index and check.get("ok") is True
                current["result_count"] += int(check.get("result_count") or 0)
                current["indexes_checked"] += 1
                if check.get("status") not in (None, "ok", "not_configured"):
                    current["last_error_status"] = check.get("status")
            for article in (evidence.get("articles") or [])[:2]:
                if isinstance(article, dict):
                    all_articles.append({
                        "index": index,
                        "title": str(article.get("title") or "")[:400],
                        "url": article.get("url"),
                        "published_at": article.get("published_at"),
                        "source": article.get("source"),
                        "content": str(article.get("content") or "")[:450],
                    })

        # Add market data only as explicitly timestamped context; stale quotes
        # are labeled stale and must never be presented as current prices.
        market_context: dict[str, Any] = {}
        try:
            with _lock:
                snapshot = dict(_signal_cache or {})
                snapshot_age = time.monotonic() - _signal_cache_at if _signal_cache is not None else None
            snapshot_is_fresh = snapshot_age is not None and snapshot_age < SIGNAL_CACHE_SECONDS
            for index in INDEXES:
                row = dict((snapshot.get("market") or {}).get(index) or {})
                quote_is_live = snapshot_is_fresh and row.get("live") is True
                market_context[index] = {
                    "ltp": row.get("ltp") if quote_is_live else None,
                    "live": quote_is_live,
                    "source_timestamp": row.get("source_timestamp") or row.get("timestamp"),
                    "age_seconds": row.get("age_seconds"),
                    "snapshot_age_seconds": round(snapshot_age, 1) if snapshot_age is not None else None,
                    "day_move_pct": row.get("day_move_pct") if quote_is_live else None,
                    "sentiment_label": row.get("sentiment_label") if quote_is_live else None,
                    "pcr": row.get("pcr") if quote_is_live else None,
                    "data_status": "LIVE" if quote_is_live else "STALE_OR_UNAVAILABLE",
                }
        except Exception:
            market_context = {index: {"data_status": "UNAVAILABLE", "ltp": None, "live": False} for index in INDEXES}

        unique_articles: list[dict[str, Any]] = []
        seen: set[str] = set()
        for article in all_articles:
            key = str(article.get("url") or article.get("title") or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique_articles.append(article)
        unique_articles = unique_articles[:18]

        api_key = (os.getenv("NVIDIA_API_KEY") or "").strip()
        summary: str | None = None
        summary_provider: str | None = None
        summary_model: str | None = None
        summary_error: str | None = None
        if api_key:
            model = os.getenv("NVIDIA_CHAT_MODEL", "z-ai/glm-5.3").strip()
            endpoint = os.getenv("NVIDIA_CHAT_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions").strip()
            messages = [
                {"role": "system", "content": (
                    "You are NVIDIA-powered market intelligence for Indian markets. Summarize what is happening "
                    "across NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX and BANKEX from the supplied fresh news "
                    "and explicitly timestamped market context. Report key themes, bullish/bearish/mixed impact, "
                    "affected sectors/indexes, important risks and what evidence is missing. Cite supplied headline "
                    "titles and source names. Never invent facts, prices, timestamps, OI or events. If quotes are "
                    "stale/unavailable, say so. This is research, not a buy/sell recommendation; never override "
                    "deterministic risk gates or claim an order should be placed."
                )},
                {"role": "user", "content": "Refresh interval: 15 minutes. Snapshot UTC: " + observed_at +
                 "\nMarket context and source-backed headlines JSON:\n" +
                 json.dumps({"market_context": market_context, "index_news": index_news, "articles": unique_articles}, separators=(",", ":"), default=str)[:14000]},
            ]
            try:
                result = _run_openai_compatible_completion(
                    api_key, model, messages, provider="nvidia", endpoint=endpoint,
                )
                summary = str(result.get("answer") or "").strip() or None
                summary_provider = "nvidia" if summary else None
                summary_model = result.get("model") if summary else None
                if not summary:
                    summary_error = "nvidia_empty_response"
            except Exception as exc:
                summary_error = str(exc)[:100] or "nvidia_inference_failed"
        else:
            summary_error = "NVIDIA_API_KEY_NOT_CONFIGURED"

        now = _utc_now()
        next_refresh = (datetime.fromisoformat(observed_at) + timedelta(seconds=MARKET_INTELLIGENCE_REFRESH_SECONDS)).isoformat()
        status = "READY" if summary and unique_articles else (
            "NVIDIA_SUMMARY_WITHOUT_NEWS" if summary else
            "NEWS_READY_NVIDIA_UNAVAILABLE" if unique_articles else "REFRESH_FAILED"
        )
        new_state = {
            "status": status,
            "summary": summary,
            "articles": unique_articles,
            "market_context": market_context,
            "index_news": index_news,
            "provider_checks": provider_checks,
            "updated_at": now.isoformat(),
            "next_refresh_at": next_refresh,
            "refresh_interval_seconds": MARKET_INTELLIGENCE_REFRESH_SECONDS,
            "summary_provider": summary_provider,
            "summary_model": summary_model,
            "summary_error": summary_error,
            "error": None if unique_articles else "No source-backed news returned by Exa/Tavily.",
            "signal_only": True,
            "order_placement_enabled": False,
        }
        with _market_intel_lock:
            _market_intel_state = new_state
    except Exception as exc:
        with _market_intel_lock:
            _market_intel_state = {
                **_market_intel_state,
                "status": "REFRESH_FAILED",
                "updated_at": _utc_now().isoformat(),
                "next_refresh_at": (_utc_now() + timedelta(seconds=MARKET_INTELLIGENCE_REFRESH_SECONDS)).isoformat(),
                "error": f"refresh_failed:{type(exc).__name__}",
            }
    finally:
        with _market_intel_lock:
            _market_intel_refreshing = False


def _market_intelligence_scheduler() -> None:
    while True:
        cycle_started = time.monotonic()
        _refresh_market_intelligence_once()
        remaining = MARKET_INTELLIGENCE_REFRESH_SECONDS - (time.monotonic() - cycle_started)
        time.sleep(max(1.0, remaining))


def _ensure_market_intelligence_scheduler() -> None:
    global _market_intel_thread
    with _market_intel_lock:
        if _market_intel_thread is not None and _market_intel_thread.is_alive():
            return
        _market_intel_thread = threading.Thread(
            target=_market_intelligence_scheduler,
            name="market-intelligence-15m",
            daemon=True,
        )
        thread = _market_intel_thread
    thread.start()


@app.on_event("startup")
def _start_market_intelligence_scheduler_on_startup() -> None:
    enabled = os.getenv("MARKET_INTELLIGENCE_AUTO_REFRESH", "true").strip().lower()
    if enabled not in {"0", "false", "no", "off"}:
        _ensure_market_intelligence_scheduler()


@app.get("/v1/market-intelligence")
def market_intelligence(_: str = Depends(_device)) -> dict[str, Any]:
    """Return the latest Exa/Tavily evidence and NVIDIA's scheduled market summary."""
    _ensure_market_intelligence_scheduler()
    with _market_intel_lock:
        return {**_market_intel_state, "refreshing": _market_intel_refreshing}


@app.post("/v1/market-intelligence/refresh")
def refresh_market_intelligence(_: str = Depends(_device)) -> dict[str, Any]:
    """Trigger a best-effort refresh; return immediately while the worker runs."""
    _ensure_market_intelligence_scheduler()
    with _market_intel_lock:
        is_refreshing = _market_intel_refreshing
        current = {**_market_intel_state, "refreshing": _market_intel_refreshing}
    if not is_refreshing:
        threading.Thread(
            target=_refresh_market_intelligence_once,
            name="market-intelligence-manual-refresh",
            daemon=True,
        ).start()
    return {**current, "refreshing": True}


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
    # Railway deployments have historically used ANGEL_CLIENT_ID while older
    # setups used ANGEL_CLIENT_CODE. Accept both names without exposing values.
    values = {
        "angel_api_key": os.getenv("ANGEL_API_KEY", "").strip(),
        "angel_client_code": (
            os.getenv("ANGEL_CLIENT_CODE", "").strip()
            or os.getenv("ANGEL_CLIENT_ID", "").strip()
        ),
        "angel_pin": os.getenv("ANGEL_PIN", "").strip(),
        "angel_totp_secret": os.getenv("ANGEL_TOTP_SECRET", "").strip(),
    }
    return {key: value for key, value in values.items() if value}


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


def _commodity_contract_matches(row: dict[str, Any], requested: str) -> bool:
    """Match a requested MCX future to its instrument-master name/symbol without mixing mini and standard contracts."""
    key = requested.strip().upper()
    name = str(row.get("name", "")).upper().replace(" ", "")
    symbol = str(row.get("symbol", "")).upper()
    if key == "CRUDEOIL":
        return (name == key or symbol.startswith(key)) and not symbol.startswith("CRUDEOILM")
    if key == "CRUDEOILM":
        return symbol.startswith(key)
    if key in {"GOLD", "SILVER"}:
        return (name == key or symbol.startswith(key)) and not symbol.startswith(key + "M")
    if key in {"GOLDM", "SILVERM"}:
        return symbol.startswith(key)
    if key == "NATURALGAS":
        return name == key or symbol.startswith(key)
    if key == "NATGASMINI":
        return symbol.startswith(key)
    return name == key or symbol.startswith(key)


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
                and _commodity_contract_matches(row, name)
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
            _stream = AngelOneStream(adapter, on_tick=publish_angelone_tick)
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

def _book_sides(quote: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return only broker-reported best-five bid/ask levels; never synthesize levels."""
    raw = quote.get("best5Data") or quote.get("depth") or {}
    if isinstance(raw, list):
        buy = [x for x in raw if isinstance(x, dict) and str(x.get("side", "")).lower() in ("buy", "b")]
        sell = [x for x in raw if isinstance(x, dict) and str(x.get("side", "")).lower() in ("sell", "s")]
    elif isinstance(raw, dict):
        buy = raw.get("buy") or raw.get("bids") or []
        sell = raw.get("sell") or raw.get("asks") or []
    else:
        buy, sell = [], []
    return ([x for x in buy if isinstance(x, dict)], [x for x in sell if isinstance(x, dict)])


def _footprint_levels(quote: dict[str, Any], step: float = 5.0) -> tuple[dict[str, list[float]], int, int]:
    """Bucket real best-five book quantities into the original chart's price rows.

    Values are [sell-side ask depth, buy-side bid depth], not exchange-classified
    trade prints. Missing broker levels produce an empty map rather than fake cells.
    """
    buy, sell = _book_sides(quote)
    levels: dict[str, list[float]] = {}
    def bucket(price: float) -> str:
        value = round(price / step) * step if step > 0 else price
        return f"{value:.2f}"
    for rows, side_index in ((sell, 0), (buy, 1)):
        for row in rows:
            price = _number(row.get("price"))
            quantity = _number(row.get("quantity"))
            if price is None or price <= 0 or quantity is None or quantity < 0:
                continue
            key = bucket(price)
            pair = levels.setdefault(key, [0.0, 0.0])
            pair[side_index] += quantity
    buy_orders = sum(int(_number(row.get("orders") or row.get("orderCount") or row.get("numberOfOrders")) or 0) for row in buy)
    sell_orders = sum(int(_number(row.get("orders") or row.get("orderCount") or row.get("numberOfOrders")) or 0) for row in sell)
    return levels, buy_orders, sell_orders


def _footprint_chart_step(symbol: str) -> float:
    """Price bucket size for display; this does not imply exchange trade-print data."""
    return {
        "CRUDEOIL": 1.0, "CRUDEOILM": 1.0, "NATURALGAS": 0.5, "NATGASMINI": 0.5,
        "GOLD": 100.0, "GOLDM": 10.0, "SILVER": 100.0, "SILVERM": 10.0,
        "COPPER": 1.0, "ZINC": 0.5, "ALUMINIUM": 0.5, "LEAD": 0.5,
        "NICKEL": 1.0, "MENTHAOIL": 1.0, "CASTORSEED": 10.0, "COTTON": 10.0, "RUBBER": 1.0,
        "BANKNIFTY": 10.0, "SENSEX": 20.0, "BANKEX": 20.0,
    }.get(symbol.strip().upper(), 5.0)


def _find_nearest_future(rows: list[dict[str, Any]], index: str) -> dict[str, str] | None:
    """Find nearest unexpired index or MCX commodity future from the broker master."""
    key = index.strip().upper()
    commodity_names = {"CRUDEOIL", "CRUDEOILM", "NATURALGAS", "NATGASMINI", "GOLD", "GOLDM", "SILVER", "SILVERM", "COPPER", "ZINC", "ALUMINIUM", "LEAD", "NICKEL", "MENTHAOIL", "CASTORSEED", "COTTON", "RUBBER"}
    is_commodity = key in commodity_names
    segment = "MCX" if is_commodity else ("BFO" if key in {"SENSEX", "BANKEX"} else "NFO")
    today = datetime.now(IST).date()
    contracts = []
    for row in rows:
        row_segment = str(row.get("exch_seg", "")).upper()
        row_name = str(row.get("name", "")).upper().replace(" ", "")
        instrument_type = str(row.get("instrumenttype", "")).upper()
        symbol = str(row.get("symbol", "")).upper()
        if row_segment != segment or not row.get("token"):
            continue
        if is_commodity:
            # MCX commodity futures are FUTCOM. Accept exact master name or
            # exact symbol prefix so mini contracts resolve to their own token.
            matches = row_name == key or symbol.startswith(key)
            if not matches or instrument_type != "FUTCOM":
                continue
        elif row_name != key or instrument_type != "FUTIDX":
            continue
        expiry = _expiry_date(row.get("expiry"))
        if expiry is None or expiry < today:
            continue
        contracts.append(row)
    contracts.sort(key=lambda row: _expiry_date(row.get("expiry")) or date.max)
    if not contracts:
        return None
    row = contracts[0]
    return {"exchange": segment, "token": str(row["token"]), "symbol": str(row.get("symbol") or key), "expiry": str(row.get("expiry") or "")}


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
            # Use a broker tick only when it includes a two-sided book. Otherwise
            # fall back to rate-limited REST FULL quotes; never synthesize depth.
            if bid is not None and ask is not None:
                output[token] = tick
    missing = [token for token in unique_tokens if token not in output]
    # SmartAPI market-data accepts at most 50 tokens per exchange in one request.
    # Chunking prevents HTTP 400 loops on 100-contract MCX option chains.
    for offset in range(0, len(missing), 50):
        batch = missing[offset:offset + 50]
        try:
            result = adapter.market_data("FULL", {exchange: batch})
            for row in _quote_rows(result):
                token = str(row.get("symbolToken") or row.get("symboltoken") or row.get("token") or "")
                if token:
                    row["_source_mode"] = "REST_FULL_DEPTH"
                    output[token] = row
        except Exception:
            # Preserve any real ticks already collected. If no quote succeeded,
            # let the route return a typed data error instead of an empty success.
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
    """A blocked/missing-data signal still returns the full validation contract."""
    return {
        "decision": "WAIT", "candidate_decision": "WAIT", "index": index,
        "entry": None, "stop_loss": None, "target": None, "strike": None,
        "expiry": None, "signal_only": True, "layers": {},
        "reasons": [reason], "signal_stability": {"state": "BLOCKED", "required_minutes": 10},
        "data_source": "angelone_smartapi", "data_fresh": False,
        "five_layer_engine": {"layers": {}, "decision": "WAIT", "passed_layers": 0, "total_layers": 0},
        "quant_engine": {"layers": {}, "decision": "WAIT", "passed_layers": 0, "total_layers": 0},
        "live_validation": {
            "decision": "WAIT", "verdict": "WAIT",
            "checks": {
                "fresh_market_data": False, "valid_option_quote": False,
                "five_layer_engine": False, "valid_sl_target": False,
                "risk_checks": False, "ai_direction_consistent": False,
            },
            "market_direction": "UNKNOWN", "market_age_seconds": None,
            "option_age_seconds": None, "reward_risk": None,
            "ai_decision": "NOT_RUN", "blocks": ["NO_LIVE_MARKET_DATA", reason],
            "ai_conflict": False, "signal_only": True, "order_placement_enabled": False,
        },
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


def _live_validation_contract(
    result: dict[str, Any],
    engine_layers: dict[str, Any],
    option_age_seconds: Any,
    ai_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return explicit fail-closed checks for the Flutter Risk & Validation panel."""
    candidate = str(result.get("decision") or "WAIT").upper()
    is_candidate = candidate in ("CALL BUY", "PUT BUY")
    data_layer = dict(engine_layers.get("data_quality") or {})
    option_layer = dict(engine_layers.get("option_selection") or {})
    risk_layer = dict(engine_layers.get("risk_levels") or {})
    age = _number(data_layer.get("age_seconds"))
    option_age = _number(option_age_seconds)
    fresh_market = data_layer.get("pass") is True and age is not None and 0 <= age <= 60
    valid_option_quote = option_layer.get("pass") is True and option_age is not None and 0 <= option_age <= 60
    entry = _number(result.get("entry"))
    stop = _number(result.get("stop_loss"))
    target = _number(result.get("target"))
    valid_levels = entry is not None and stop is not None and target is not None and 0 < stop < entry < target
    five_layer_pass = len(engine_layers) >= 5 and all(
        isinstance(layer, dict) and layer.get("pass") is True for layer in engine_layers.values()
    )
    risk_pass = risk_layer.get("pass") is True
    ai_conflict = False
    ai_decision = "NOT_RUN"
    if isinstance(ai_review, dict) and (ai_review.get("ok") is True or ai_review.get("validated") is True):
        ai_decision = str(ai_review.get("decision") or ai_review.get("action") or "WAIT").upper()
        if ai_decision in ("WAIT", "REJECT", "CALL BUY", "PUT BUY"):
            ai_conflict = ai_decision != candidate
    checks = {
        "fresh_market_data": fresh_market,
        "valid_option_quote": valid_option_quote,
        "five_layer_engine": five_layer_pass,
        "valid_sl_target": valid_levels,
        "risk_checks": risk_pass,
        "ai_direction_consistent": not ai_conflict,
    }
    blocks = [name.upper() for name, passed in checks.items() if not passed]
    if not is_candidate:
        blocks.append("NO_QUALIFIED_STRATEGY_CANDIDATE")
    final_pass = is_candidate and all(checks.values())
    return {
        "decision": candidate if final_pass else "WAIT",
        "verdict": "PASS" if final_pass else "WAIT",
        "checks": checks,
        "market_direction": (dict(engine_layers.get("trend_sentiment") or {}).get("trend") or "UNKNOWN"),
        "market_age_seconds": age,
        "option_age_seconds": option_age,
        "reward_risk": risk_layer.get("reward_risk") or risk_layer.get("risk_reward"),
        "ai_decision": ai_decision,
        "blocks": blocks,
        "ai_conflict": ai_conflict,
        "signal_only": True,
        "order_placement_enabled": False,
    }

def _aggregate_hourly_chart_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate complete same-session 5-minute bars; never bridge overnight gaps."""
    buckets: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        try:
            parsed = datetime.fromisoformat(str(row.get("timestamp", "")))
            local = parsed.astimezone(IST)
            session_minute = local.hour * 60 + local.minute - (9 * 60 + 15)
            if session_minute < 0 or session_minute >= 375:
                continue
            key = (local.date().isoformat(), session_minute // 60)
            buckets.setdefault(key, []).append(row)
        except (TypeError, ValueError):
            continue
    result: list[dict[str, Any]] = []
    for key in sorted(buckets):
        group = sorted(buckets[key], key=lambda item: int(item.get("t") or 0))
        # Require all twelve 5-minute bars so partial hours never masquerade as 1H.
        if len(group) != 12:
            continue
        volumes = [_number(item.get("volume")) for item in group]
        result.append({
            "t": group[-1]["t"], "timestamp": group[-1]["timestamp"],
            "open": group[0]["open"], "high": max(item["high"] for item in group),
            "low": min(item["low"] for item in group), "close": group[-1]["close"],
            "volume": sum(value for value in volumes if value is not None) if any(value is not None for value in volumes) else None,
        })
    return result


def _aggregate_weekly_chart_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate real daily bars into ISO-week OHLCV; no synthetic weekly candles."""
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        try:
            parsed = datetime.fromisoformat(str(row.get("timestamp", ""))).astimezone(IST)
            iso = parsed.isocalendar()
            buckets.setdefault((iso.year, iso.week), []).append(row)
        except (TypeError, ValueError):
            continue
    result: list[dict[str, Any]] = []
    for key in sorted(buckets):
        group = sorted(buckets[key], key=lambda item: int(item.get("t") or 0))
        if not group:
            continue
        volumes = [_number(item.get("volume")) for item in group]
        result.append({
            "t": group[-1]["t"], "timestamp": group[-1]["timestamp"],
            "open": group[0]["open"], "high": max(item["high"] for item in group),
            "low": min(item["low"] for item in group), "close": group[-1]["close"],
            "volume": sum(value for value in volumes if value is not None) if any(value is not None for value in volumes) else None,
        })
    return result


def _apply_strategy_confluence_filter(
    result: dict[str, Any],
    strategy_suite: dict[str, Any],
    execution_id: str,
) -> dict[str, Any]:
    """Make the completed-candle strategy consensus a mandatory live-signal gate.

    Strategy LONG must agree with the Quant Engine CALL BUY candidate; SHORT
    must agree with PUT BUY. A mismatch keeps the response signal-only WAIT and
    removes actionable levels while preserving the proposal for diagnostics.
    """
    candidate = str(result.get("candidate_decision") or result.get("decision") or "WAIT").strip().upper()
    expected_side = {"CALL BUY": "LONG", "PUT BUY": "SHORT"}.get(candidate)
    strategy_side = str(strategy_suite.get("signal") or "WAIT").strip().upper()
    votes = strategy_suite.get("votes") if isinstance(strategy_suite.get("votes"), dict) else {}
    long_votes = int(votes.get("LONG") or 0)
    short_votes = int(votes.get("SHORT") or 0)
    expected_votes = long_votes if expected_side == "LONG" else short_votes
    opposing_votes = short_votes if expected_side == "LONG" else long_votes
    has_candidate = expected_side is not None
    quant_gate_pass = (
        isinstance(result.get("live_validation"), dict)
        and result["live_validation"].get("verdict") == "PASS"
        and str(result.get("decision") or "").strip().upper() == candidate
        and isinstance(result.get("five_layer_engine"), dict)
        and str(result["five_layer_engine"].get("decision") or "").strip().upper() == candidate
    )
    strategy_pass = bool(
        has_candidate
        and strategy_suite.get("status") == "ok"
        and strategy_side == expected_side
        and expected_votes >= 3
        and expected_votes > opposing_votes
    )
    passed = bool(quant_gate_pass and strategy_pass)
    gate_state = (
        "PASS" if passed else
        "NO_QUANT_CANDIDATE" if not has_candidate else
        "BLOCKED_BY_QUANT_VALIDATION" if not quant_gate_pass else
        "BLOCKED_BY_STRATEGY"
    )
    gate = {
        "pass": passed,
        "state": gate_state,
        "quant_candidate": candidate,
        "expected_strategy_side": expected_side,
        "strategy_signal": strategy_side,
        "votes": {"LONG": long_votes, "SHORT": short_votes},
        "minimum_consensus": 3,
        "strategy_execution_id": execution_id,
        "source": "same_completed_5m_angelone_candles",
        "reason": (
            "Quant validation and strategy consensus agree with the candidate."
            if passed else
            "No actionable Quant candidate exists; final decision remains WAIT."
            if not has_candidate else
            "The Five-Layer Quant or live-data validation gate did not pass."
            if not quant_gate_pass else
            "Strategy consensus is missing, below three votes, or conflicts with the Quant candidate."
        ),
    }
    result["strategy_filter"] = gate
    plan = result.get("trade_plan")
    if not isinstance(plan, dict):
        plan = {}
        result["trade_plan"] = plan
    plan["strategy_filter"] = gate
    # A signal's exit field is the target-price reference, not an order or a
    # promise of execution. Keep the meaning explicit for every consumer page.
    result["exit"] = result.get("target")
    result["exit_semantics"] = "target price reference; signal-only, no order placement"
    plan["exit"] = result.get("exit")
    plan["exit_semantics"] = result["exit_semantics"]
    if has_candidate and not passed:
        result["candidate_setup"] = {
            "decision": candidate,
            "option_type": result.get("option_type"),
            "option_side": result.get("option_side"),
            "strike": result.get("strike"),
            "expiry": result.get("expiry"),
            "entry": result.get("entry"),
            "exit": result.get("exit"),
            "stop_loss": result.get("stop_loss"),
            "target": result.get("target"),
            "status": "BLOCKED_NOT_ACTIONABLE",
        }
        result["decision"] = "WAIT"
        for key in ("strike", "expiry", "entry", "exit", "stop_loss", "target", "option_type", "option_side"):
            result[key] = None
        plan.update({
            "selection_grade": "WAIT", "strike": None, "expiry": None,
            "entry": None, "exit": None, "stop_loss": None, "target": None,
        })
        stability = result.get("signal_stability")
        if isinstance(stability, dict):
            stability["state"] = "BLOCKED_BY_QUANT_VALIDATION" if not quant_gate_pass else "BLOCKED_BY_STRATEGY"
        reasons = list(result.get("reasons") or [])
        reasons.append(("QUANT_VALIDATION_BLOCKED: " if not quant_gate_pass else "STRATEGY_CONFLUENCE_BLOCKED: ") + gate["reason"])
        result["reasons"] = list(dict.fromkeys(reasons))
        result["reason"] = list(result["reasons"])
        result["guards"] = list(result["reasons"])
        validation = result.get("live_validation")
        if isinstance(validation, dict):
            blocks = list(validation.get("blocks") or [])
            blocks.append("QUANT_VALIDATION_BLOCKED" if not quant_gate_pass else "STRATEGY_CONFLUENCE_BLOCKED")
            validation["blocks"] = list(dict.fromkeys(blocks))
            validation["verdict"] = "BLOCKED"
    elif not has_candidate:
        # WAIT/no-candidate responses must not leak old levels from a prior setup.
        for key in ("strike", "expiry", "entry", "exit", "stop_loss", "target", "option_type", "option_side"):
            result[key] = None
        plan.update({
            "selection_grade": "WAIT", "strike": None, "expiry": None,
            "entry": None, "exit": None, "stop_loss": None, "target": None,
        })
    engine = result.get("five_layer_engine")
    if isinstance(engine, dict):
        engine["decision"] = result.get("decision", "WAIT")
        result["quant_engine"] = engine
    return result


def _completed_candle_rows(
    rows: list[dict[str, Any]],
    timeframe_minutes: int = 5,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Drop candles whose start + timeframe has not elapsed yet."""
    if timeframe_minutes < 1:
        raise ValueError("timeframe_minutes must be positive")
    current = now or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    completed: list[dict[str, Any]] = []
    for row in rows:
        stamp_text = row.get("timestamp")
        try:
            stamp = datetime.fromisoformat(str(stamp_text))
        except (TypeError, ValueError):
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
        if stamp + timedelta(minutes=timeframe_minutes) <= current:
            completed.append(row)
    return completed


def _index_snapshot(
    adapter: AngelOneReadOnly,
    rows: list[dict[str, Any]],
    index: str,
    spot_quote: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = _find_index_contract(rows, index)
    start, end = _session_range()
    # Start the slower historical request while the current quote and option
    # contracts are being normalized. It is rate-limited centrally by the adapter.
    candle_future = _market_data_executor.submit(
        adapter.candles, config["exchange"], config["token"], "FIVE_MINUTE", start, end
    )
    # Fetch genuine daily history in parallel so the SMC chart's 1D timeframe
    # never aliases intraday candles or fabricates higher-timeframe bars.
    daily_end_dt = datetime.now(IST)
    daily_start_text = (daily_end_dt - timedelta(days=45)).strftime("%Y-%m-%d %H:%M")
    daily_end_text = daily_end_dt.strftime("%Y-%m-%d %H:%M")
    daily_future = _market_data_executor.submit(
        adapter.candles, config["exchange"], config["token"], "ONE_DAY",
        daily_start_text, daily_end_text,
    )
    if spot_quote is None:
        spot_quote = _quotes(adapter, config["exchange"], [config["token"]]).get(config["token"])
    if not spot_quote:
        raise RuntimeError("Angel One did not return a spot quote for this index")
    spot = _number(spot_quote.get("ltp"))
    if spot is None or spot <= 0:
        raise RuntimeError("Spot LTP is missing or invalid")
    spot_ts = _quote_timestamp(spot_quote)
    if not spot_ts:
        raise RuntimeError("Angel One quote omitted its exchange feed timestamp; fail-closed freshness gate")
    candle_result = candle_future.result()
    candle_rows = candle_result.get("candles") or []
    try:
        daily_candle_rows = (daily_future.result(timeout=15).get("candles") or [])
    except Exception:
        # Missing daily history remains unavailable; the SMC page must not
        # reinterpret intraday bars as daily data.
        daily_candle_rows = []
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
    greek_expiry = selected_expiry.strftime("%d%b%Y").upper()
    option_future = _market_data_executor.submit(
        _quotes, adapter, exchange, [str(row["token"]) for row in candidates[:40]]
    )
    greeks_future = _market_data_executor.submit(_greeks_map, adapter, index, greek_expiry)
    # Quote batches and Greeks use different broker endpoints/rate buckets, so
    # overlap the requests without violating either endpoint's throttle.
    option_quotes = option_future.result()
    greeks = greeks_future.result()
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
        "order_flow": {"bid": bid, "ask": ask, "ltp": spot, "bid_depth": buy_volume, "ask_depth": sell_volume, "semantics": "bid_ask_depth_not_classified_trade_volume"},
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
    engine_started = time.perf_counter()
    result = evaluate_five_layer_signal(
        snapshot,
        confirmation_state=_confirmation_states.get(index),
        max_data_age_seconds=60.0,
        confirmation_seconds=600,
        max_confirmation_gap_seconds=60,
    )
    result["performance"] = {
        **dict(result.get("performance") or {}),
        "five_layer_validation_ms": round((time.perf_counter() - engine_started) * 1000, 2),
    }
    # Publish one normalized engine contract consumed by Dashboard, Signals,
    # Risk, Trading Setup, the five-layer page and Quant Engine Lab.
    engine_layers = dict(result.get("layers") or {})
    passed_layers = sum(1 for layer in engine_layers.values() if isinstance(layer, dict) and layer.get("pass") is True)
    result["five_layer_engine"] = {
        "layers": engine_layers, "decision": result.get("decision", "WAIT"),
        "passed_layers": passed_layers, "total_layers": len(engine_layers),
        "score_semantics": "passed deterministic checks, not probability of profit",
    }
    result["quant_engine"] = result["five_layer_engine"]
    result["quant_score"] = passed_layers
    result["quant_score_semantics"] = "count of passed deterministic layers; not a win probability"
    result["trend_sentiment"] = engine_layers.get("trend_sentiment", {})
    result["option_validation"] = engine_layers.get("option_selection", {})
    result["risk_validation"] = engine_layers.get("risk_levels", {})
    result["regime"] = (engine_layers.get("trend_sentiment") or {}).get("trend", "UNKNOWN")
    result["order_flow"] = {
        **snapshot["order_flow"],
        **(engine_layers.get("order_flow") or {}),
        "semantics": "bid_ask_depth_not_classified_trade_volume",
    }
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
    option_age_seconds = next((item.get("age_seconds") for item in chain_payload if item.get("strike") == result.get("strike")), None)
    live_validation = _live_validation_contract(result, engine_layers, option_age_seconds)
    if live_validation["verdict"] != "PASS":
        if result.get("decision") in ("CALL BUY", "PUT BUY"):
            result["candidate_decision"] = result.get("decision")
        result["decision"] = "WAIT"
        result["five_layer_engine"]["decision"] = "WAIT"
        result["quant_engine"] = result["five_layer_engine"]
        result["trade_plan"]["selection_grade"] = "WAIT"
        existing_reasons = list(result.get("reasons") or [])
        existing_reasons.extend("VALIDATION_BLOCKED:" + item for item in live_validation["blocks"])
        result["reasons"] = list(dict.fromkeys(existing_reasons))
    result["live_validation"] = live_validation
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
    # Do not feed an in-progress 5-minute candle to indicators or strategy votes.
    chart_5m = _completed_candle_rows(chart_5m, timeframe_minutes=5)
    chart_5m = chart_5m[-250:]
    chart_1h = _aggregate_hourly_chart_rows(chart_5m)
    chart_1d: list[dict[str, Any]] = []
    for candle in daily_candle_rows:
        if not isinstance(candle, (list, tuple)) or len(candle) < 6:
            continue
        stamp = _iso(candle[0])
        parsed_stamp = datetime.fromisoformat(stamp) if stamp else None
        opened, high, low, closed = (_number(candle[i]) for i in (1, 2, 3, 4))
        if parsed_stamp is None or any(value is None for value in (opened, high, low, closed)):
            continue
        chart_1d.append({
            "t": int(parsed_stamp.timestamp()), "timestamp": stamp,
            "open": opened, "high": high, "low": low, "close": closed,
            "volume": _number(candle[5]),
        })
    chart_1d = chart_1d[-45:]
    chart_1w = _aggregate_weekly_chart_rows(chart_1d)
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
    # Run the full local research suite against the same completed 5m
    # Angel One candles exposed to the app. Attach a reproducible execution
    # trace so downstream AI can be told exactly which output entered context.
    strategy_suite = evaluate_strategy_suite(chart_5m, oi_change=None)
    strategy_hash = hashlib.sha256(
        json.dumps(chart_5m, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    strategy_execution_id = f"strategy-{uuid.uuid4().hex}"
    strategy_trace = {
        "execution_id": strategy_execution_id,
        "strategy_version": "strategy-suite-v1",
        "evaluated_at": _utc_now().isoformat(),
        "input_candle_count": len(chart_5m),
        "input_sha256": strategy_hash,
        "source": "angelone_completed_5m_candles",
        "ai_context_sent": False,
        "ai_semantic_use_verifiable": False,
        "research_engine_received": False,
        "trading_setup_received": False,
        "order_placement_enabled": False,
    }
    strategy_trace_rows = []
    for strategy_name, strategy_signal in (strategy_suite.get("strategies") or {}).items():
        strategy_signal = str(strategy_signal or "WAIT").upper()
        strategy_trace_rows.append({
            "strategy_id": f"{strategy_execution_id}:{strategy_name}",
            "strategy_name": strategy_name,
            "strategy_version": "strategy-suite-v1",
            "execution_id": strategy_execution_id,
            "signal": strategy_signal,
            "score": None,
            "score_status": "NOT_COMPUTED_BY_RULE",
            "input_candle_count": len(chart_5m),
            "input_sha256": strategy_hash,
            "source": "angelone_completed_5m_candles",
            "status": "evaluated",
            "rejection_reason": None if strategy_signal in ("LONG", "SHORT") else (
                "No directional LONG/SHORT event was returned for the final completed candle; WAIT is not a trade."
            ),
            "ai_context_sent": False,
            "ai_semantic_use_verifiable": False,
            "research_engine_received": False,
            "trading_setup_received": False,
            "order_placement_enabled": False,
        })
    strategy_suite["execution_id"] = strategy_execution_id
    # Do not claim downstream delivery merely because the suite was computed.
    # The shared signal payload exposes the result; separate page-level receipt
    # must be instrumented by the actual consumers before these flags turn true.
    strategy_trace["shared_signal_payload_available"] = True
    strategy_trace["research_engine_received"] = False
    strategy_trace["trading_setup_received"] = False
    for trace_row in strategy_trace_rows:
        trace_row["shared_signal_payload_available"] = True
        trace_row["research_engine_received"] = False
        trace_row["trading_setup_received"] = False
    strategy_suite["trace"] = strategy_trace
    strategy_suite["strategy_trace"] = strategy_trace_rows
    result = _apply_strategy_confluence_filter(result, strategy_suite, strategy_execution_id)
    result["strategy_suite"] = strategy_suite
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
        "timeframes": {"1m": [], "5m": chart_5m, "15m": chart_15m, "1H": chart_1h, "1D": chart_1d, "1W": chart_1w},
        "option_chain": chain_payload,
        "strategy_suite": result["strategy_suite"],
    }
    return result, market


def _empty_payload(reason: str) -> dict[str, Any]:
    now = _utc_now().isoformat()
    return {
        "live": False, "last_fetch": None, "message": reason,
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
    """Stream broker-only nearest-future snapshots without running the slow signal fan-out."""
    await websocket.accept()
    symbol = (websocket.query_params.get("symbol") or "NIFTY").strip().upper()
    timeframe = (websocket.query_params.get("tf") or "1").strip().lower()
    daily_mode = timeframe in {"1440", "10080", "1d", "1w", "d", "day", "week", "w"}
    history_mode = "ONE_DAY" if daily_mode else "ONE_MINUTE"
    max_candles = 2000 if daily_mode else 500
    supported_symbols = set(INDEXES) | {"CRUDEOIL", "CRUDEOILM", "NATURALGAS", "NATGASMINI", "GOLD", "GOLDM", "SILVER", "SILVERM", "COPPER", "ZINC", "ALUMINIUM", "LEAD", "NICKEL", "MENTHAOIL", "CASTORSEED", "COTTON", "RUBBER"}
    if symbol not in supported_symbols:
        await websocket.send_json({"type": "status", "mode": "wait", "message": "Unsupported index or commodity symbol"})
        await websocket.close(code=1008)
        return
    with _lock:
        candles: list[dict[str, Any]] = (
            [dict(item) for item in _footprint_history.get(symbol, [])]
            if _footprint_history_interval.get(symbol) == history_mode else []
        )
    if not daily_mode:
        # Intraday views must show this whole session, not the last 250 minutes
        # carried over from a prior day. Keep same-day cached candles on tab changes.
        today = datetime.now(IST).date()
        candles = [
            item for item in candles
            if datetime.fromtimestamp(int(item.get("t") or 0), IST).date() == today
        ]
    last_trade_volume: float | None = None
    last_source_timestamp: str | None = None
    future: dict[str, str] | None = None
    rows: list[dict[str, Any]] = []
    history_loaded = bool(candles)
    daily_history_sent = False
    try:
        while True:
            try:
                adapter = _current_adapter()
                if not adapter or adapter.status().get("authenticated") is not True:
                    await websocket.send_json({
                        "type": "snap", "symbol": symbol, "candles": candles, "step": _footprint_chart_step(symbol),
                        "mode": "wait", "live": False, "source_timestamp": None,
                        "message": "Angel One is not authenticated. Connect the broker to receive footprint data.",
                        "level_semantics": "broker_best5_bid_ask_depth_not_trade_prints",
                    })
                    await asyncio.sleep(5)
                    continue
                if not rows:
                    rows = _load_master()
                if future is None:
                    # Daily multi-year index history belongs to the underlying
                    # index token, not the current expiring index-futures token.
                    if daily_mode and symbol in INDEXES:
                        future = {**INDEXES[symbol], "symbol": symbol, "expiry": ""}
                    else:
                        future = _find_nearest_future(rows, symbol)
                if future is None:
                    await websocket.send_json({
                        "type": "snap", "symbol": symbol, "candles": candles, "step": _footprint_chart_step(symbol),
                        "mode": "wait", "live": False, "source_timestamp": None,
                        "message": "No unexpired index-futures contract found in the Angel One instrument master.",
                        "level_semantics": "broker_best5_bid_ask_depth_not_trade_prints",
                    })
                    await asyncio.sleep(5)
                    continue
                if not history_loaded:
                    history_loaded = True
                    try:
                        if daily_mode:
                            history_end_dt = datetime.now(IST)
                            history_start_dt = history_end_dt - timedelta(days=1825)
                            history_start = history_start_dt.strftime("%Y-%m-%d %H:%M")
                            history_end = history_end_dt.strftime("%Y-%m-%d %H:%M")
                            history_interval = "ONE_DAY"
                        else:
                            history_start, history_end = _session_range()
                            history_interval = "ONE_MINUTE"
                        history = adapter.candles(
                            future["exchange"], future["token"], history_interval, history_start, history_end
                        ).get("candles") or []
                        for candle in history:
                            if not isinstance(candle, (list, tuple)) or len(candle) < 6:
                                continue
                            stamp = _iso(candle[0])
                            parsed_candle = datetime.fromisoformat(stamp) if stamp else None
                            values = [_number(candle[pos]) for pos in (1, 2, 3, 4)]
                            if parsed_candle is None or any(value is None for value in values):
                                continue
                            if daily_mode:
                                local_day = parsed_candle.astimezone(IST).date()
                                bar_time = datetime.combine(local_day, dt_time(9, 0), tzinfo=IST)
                                candle_epoch = int(bar_time.timestamp())
                            else:
                                candle_epoch = int(parsed_candle.timestamp())
                            if any(int(item.get("t") or 0) == candle_epoch for item in candles):
                                continue
                            opened, high, low, close = values
                            candles.append({
                                "t": candle_epoch, "o": opened, "h": high, "l": low, "c": close,
                                "v": _number(candle[5]) or 0.0, "lv": {}, "source_timestamp": stamp,
                                "historical": True,
                                "level_semantics": "price-level depth unavailable for historical candles",
                            })
                        candles.sort(key=lambda item: int(item.get("t") or 0))
                        candles = candles[-max_candles:]
                    except Exception:
                        # Broker history can be shorter than requested; never synthesize missing bars.
                        candles = sorted(candles, key=lambda item: int(item.get("t") or 0))[-max_candles:]
                quote = _quotes(adapter, future["exchange"], [future["token"]]).get(future["token"])
                ltp = _number(quote.get("ltp")) if quote else None
                source_timestamp = _quote_timestamp(quote or {})
                parsed = datetime.fromisoformat(source_timestamp) if source_timestamp else None
                age = (_utc_now() - parsed).total_seconds() if parsed else None
                live = ltp is not None and ltp > 0 and age is not None and 0 <= age <= 60 and _is_market_session_open(symbol)
                if live and parsed and source_timestamp:
                    epoch = int(parsed.timestamp())
                    minute = epoch - epoch % 60
                    bar_time = int(datetime.combine(parsed.astimezone(IST).date(), dt_time(9, 0), tzinfo=IST).timestamp()) if daily_mode else minute
                    levels, buy_orders, sell_orders = _footprint_levels(quote or {}, step=_footprint_chart_step(symbol))
                    _, _, buy_depth, sell_depth = _book(quote or {})
                    total_volume = _number((quote or {}).get("tradeVolume") or (quote or {}).get("volume"))
                    delta_volume = max(0.0, total_volume - last_trade_volume) if total_volume is not None and last_trade_volume is not None else 0.0
                    if total_volume is not None:
                        last_trade_volume = total_volume
                    existing = next((item for item in reversed(candles) if int(item.get("t") or 0) == bar_time), None)
                    if existing is None:
                        existing = {
                            "t": bar_time, "o": ltp, "h": ltp, "l": ltp, "c": ltp,
                            "v": delta_volume, "d": buy_depth - sell_depth,
                            "bo": buy_orders, "so": sell_orders, "lv": levels,
                            "source_timestamp": source_timestamp,
                            "volume_semantics": "incremental_broker_trade_volume",
                            "level_semantics": "broker_best5_bid_ask_depth_not_trade_prints",
                        }
                        candles.append(existing)
                    else:
                        existing["h"] = max(float(existing["h"]), ltp)
                        existing["l"] = min(float(existing["l"]), ltp)
                        existing["c"] = ltp
                        if not (daily_mode and existing.get("historical") is True):
                            existing["v"] = delta_volume if existing.get("historical") is True else float(existing.get("v") or 0) + delta_volume
                        existing.pop("historical", None)
                        existing["d"] = buy_depth - sell_depth
                        existing["bo"] = buy_orders
                        existing["so"] = sell_orders
                        existing["lv"] = levels
                        existing["source_timestamp"] = source_timestamp
                    candles = candles[-max_candles:]
                    last_source_timestamp = source_timestamp
                if candles:
                    with _lock:
                        _footprint_history[symbol] = [dict(item) for item in candles[-max_candles:]]
                        _footprint_history_interval[symbol] = history_mode
                mode = "live" if live else ("closed" if candles else "wait")
                snapshot_message = (
                    f"Daily chart requested 1825 days; broker returned {len(candles)} candle(s). "
                    "Coverage depends on the selected instrument's historical retention; no synthetic bars are created. "
                    "MCX current-contract history may not span five years."
                    if daily_mode else
                    "Live requires a fresh exchange timestamp. Footprint cells show broker best-five bid/ask depth, not classified trade prints."
                )
                snapshot_payload = {
                    "type": "snap", "symbol": symbol, "candles": candles, "step": _footprint_chart_step(symbol),
                    "mode": mode, "live": live, "ltp": ltp if live else None,
                    "source_timestamp": source_timestamp, "tick_age_ms": int(age * 1000) if age is not None else None,
                    "future_symbol": future["symbol"], "future_expiry": future["expiry"],
                    "level_semantics": "broker_best5_bid_ask_depth_not_trade_prints",
                    "history_interval": history_mode,
                    "history_requested_days": 1825 if daily_mode else 1,
                    "history_bars_returned": len(candles),
                    "history_first_timestamp": candles[0].get("source_timestamp") if candles else None,
                    "history_last_timestamp": candles[-1].get("source_timestamp") if candles else None,
                    "message": snapshot_message,
                    "signal_only": True, "order_placement_enabled": False,
                }
                # A five-year daily payload is sent once. Subsequent five-second
                # WebSocket updates carry only the latest daily candle to avoid
                # repeatedly transferring thousands of unchanged bars.
                if daily_mode and daily_history_sent:
                    snapshot_payload["type"] = "candle"
                    snapshot_payload["candle"] = dict(candles[-1]) if candles else None
                    snapshot_payload.pop("candles", None)
                elif daily_mode:
                    daily_history_sent = True
                await websocket.send_json(snapshot_payload)
            except HTTPException as exc:
                await websocket.send_json({"type": "status", "mode": "wait", "message": str(exc.detail)[:180], "candles": candles})
            except Exception:
                await websocket.send_json({"type": "status", "mode": "wait", "message": "Broker futures snapshot unavailable; waiting for a fresh timestamped quote.", "candles": candles})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Browsers and WebViews request this implicitly; it is not an API failure."""
    return Response(status_code=204)


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
        "signal_build": dict(_signal_build_metrics),
        "api_performance": {
            path: {key: value for key, value in metric.items() if key != "total_ms"}
            for path, metric in _request_metrics.items()
        },
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
            "index_status": {
                key: {
                    "ltp_available": row.get("ltp") is not None,
                    "live": row.get("live") is True,
                    "age_seconds": row.get("age_seconds"),
                    "signal_error": row.get("signal_error") or row.get("error"),
                    "option_chain_count": len(row.get("option_chain") or []),
                    "candle_5m_count": len(((row.get("timeframes") or {}).get("5m") or [])),
                }
                for key, row in ((_signal_cache or {}).get("market") or {}).items()
                if isinstance(row, dict)
            },
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
    request_started = time.monotonic()
    cached = _option_chain_cache.get(index)
    if cached and OPTION_CHAIN_CACHE_TTL_SECONDS > 0:
        cached_at, cached_payload = cached
        cache_age = time.monotonic() - cached_at
        if cache_age <= OPTION_CHAIN_CACHE_TTL_SECONDS:
            return {
                **cached_payload,
                "cache": {"hit": True, "age_ms": round(cache_age * 1000, 1)},
                "request_elapsed_ms": round((time.monotonic() - request_started) * 1000, 1),
            }
        _option_chain_cache.pop(index, None)
    adapter = _require_adapter()
    rows = _load_master()
    commodity = index in COMMODITY_NAMES
    if not commodity and index not in INDEXES:
        raise HTTPException(status_code=400, detail=f"Unsupported underlying. Choose an index or supported MCX commodity: {', '.join(INDEXES)}; {', '.join(COMMODITY_NAMES)}.")

    if commodity:
        # MCX commodity options are OPTFUT contracts; use the nearest live
        # FUTCOM contract as underlying reference, never fabricate a spot.
        futures = [
            row for row in rows
            if str(row.get("exch_seg", "")).upper() == "MCX"
            and _commodity_contract_matches(row, index)
            and str(row.get("instrumenttype", "")).upper() == "FUTCOM"
            and _expiry_date(row.get("expiry")) is not None
            and _expiry_date(row.get("expiry")) >= datetime.now(IST).date()
        ]
        if not futures:
            raise HTTPException(status_code=404, detail=f"No unexpired MCX futures found for {index}; sync the current Angel One instrument master.")
        future_expiries = sorted({_expiry_date(row.get("expiry")) for row in futures if _expiry_date(row.get("expiry"))})
        future = next((row for row in futures if _expiry_date(row.get("expiry")) == future_expiries[0]), futures[0])
        future_token = str(future.get("token", ""))
        spot_future = _market_data_executor.submit(_quotes, adapter, "MCX", [future_token])
        try:
            spot_quote = spot_future.result(timeout=OPTION_CHAIN_UPSTREAM_TIMEOUT_SECONDS).get(future_token)
        except FutureTimeoutError:
            spot_future.cancel()
            raise HTTPException(status_code=504, detail={
                "message": "Angel One underlying quote timed out; no cached or fabricated spot was used.",
                "stage": "option_chain_underlying_quote", "timeout_seconds": OPTION_CHAIN_UPSTREAM_TIMEOUT_SECONDS,
                "retryable": True,
            })
        spot = _number(spot_quote.get("ltp")) if spot_quote else None
        segment = "MCX"
        option_instrument = "OPTFUT"
        option_name = index
    else:
        config = _find_index_contract(rows, index)
        spot_future = _market_data_executor.submit(_quotes, adapter, config["exchange"], [config["token"]])
        try:
            spot_quote = spot_future.result(timeout=OPTION_CHAIN_UPSTREAM_TIMEOUT_SECONDS).get(config["token"])
        except FutureTimeoutError:
            spot_future.cancel()
            raise HTTPException(status_code=504, detail={
                "message": "Angel One underlying quote timed out; no cached or fabricated spot was used.",
                "stage": "option_chain_underlying_quote", "timeout_seconds": OPTION_CHAIN_UPSTREAM_TIMEOUT_SECONDS,
                "retryable": True,
            })
        spot = _number(spot_quote.get("ltp")) if spot_quote else None
        segment = "BFO" if index in ("SENSEX", "BANKEX") else "NFO"
        option_instrument = "OPTIDX"
        option_name = index
    if spot is None or spot <= 0:
        raise HTTPException(status_code=502, detail=f"Angel One underlying quote is missing for {index}; no option signal can be qualified.")

    contracts = [
        row for row in rows
        if str(row.get("exch_seg", "")).upper() == segment
        and (_commodity_contract_matches(row, option_name) if commodity else str(row.get("name", "")).upper().replace(" ", "") == option_name)
        and str(row.get("instrumenttype", "")).upper() == option_instrument
        and _option_type(row) is not None
        and _expiry_date(row.get("expiry")) is not None
        and _expiry_date(row.get("expiry")) >= datetime.now(IST).date()
    ]
    expiries = sorted({_expiry_date(row.get("expiry")) for row in contracts if _expiry_date(row.get("expiry"))})
    if not expiries:
        return {"index": index, "spot": spot, "contracts": [], "option_chain": [], "status": "WAIT", "reason": f"No unexpired {option_instrument} option contracts found for {index}", "signal_only": True}
    contracts = [row for row in contracts if _expiry_date(row.get("expiry")) == expiries[0]]
    strikes = sorted({strike for row in contracts if (strike := _strike_value(row.get("strike"), spot)) is not None})
    atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot)) if strikes else 0
    wanted = set(strikes[max(0, atm - 10): min(len(strikes), atm + 11)])
    contracts = [row for row in contracts if _strike_value(row.get("strike"), spot) in wanted][:100]
    # Quotes and Greeks are independent upstream requests. Fetch them concurrently
    # to avoid serially paying both broker latencies on every option-chain refresh.
    quote_future = _market_data_executor.submit(
        _quotes, adapter, segment,
        [str(row.get("token", "")) for row in contracts if row.get("token")],
    )
    greek_future = _market_data_executor.submit(
        _greeks_map, adapter, index, expiries[0].strftime("%d%b%Y").upper(),
    )
    timed_out: list[str] = []
    # Both futures share one deadline; sequential full timeouts would double the
    # UI wait under a simultaneous broker slowdown.
    upstream_deadline = time.monotonic() + OPTION_CHAIN_UPSTREAM_TIMEOUT_SECONDS
    try:
        quote_map = quote_future.result(timeout=max(0.01, upstream_deadline - time.monotonic()))
    except FutureTimeoutError:
        quote_future.cancel()
        quote_map = {}
        timed_out.append("quotes")
    # Greeks are supplemental and may time out independently. Missing values
    # remain null; never synthesize Greeks or use them to qualify a trade.
    try:
        greek_map = greek_future.result(timeout=max(0.01, upstream_deadline - time.monotonic()))
    except FutureTimeoutError:
        greek_future.cancel()
        greek_map = {}
        timed_out.append("greeks")
    output = []
    for row in contracts:
        token = str(row.get("token", ""))
        quote = quote_map.get(token)
        if not quote:
            continue
        strike = _strike_value(row.get("strike"), spot)
        kind = _option_type(row)
        bid, ask, buy_depth, sell_depth = _book(quote)
        greek = greek_map.get((strike or -1, kind or ""), {})
        output.append({
            "symbol": row.get("symbol"), "token": token, "option_type": kind,
            "side": "CE" if kind == "CALL" else "PE" if kind == "PUT" else None,
            "strike": strike, "expiry": expiries[0].isoformat(),
            "ltp": _number(quote.get("ltp")), "bid": bid, "ask": ask,
            "volume": _number(quote.get("tradeVolume") or quote.get("volume")),
            "oi": _number(quote.get("opnInterest") or quote.get("openInterest") or quote.get("oi")),
            "delta": greek.get("delta"), "gamma": greek.get("gamma"),
            "theta": greek.get("theta"), "vega": greek.get("vega"), "iv": greek.get("iv"),
            "buy_depth": buy_depth, "sell_depth": sell_depth,
            "timestamp": _quote_timestamp(quote), "source_timestamp": _quote_timestamp(quote),
        })
    elapsed_ms = round((time.monotonic() - request_started) * 1000, 1)
    payload = {
        "index": index, "spot": spot, "expiry": expiries[0].isoformat(),
        "contracts": output, "option_chain": _market_chain_rows(output),
        "source": "angelone_smartapi", "observed_at": _utc_now().isoformat(),
        "signal_only": True, "underlying_type": "MCX_FUTURE" if commodity else "INDEX",
        "cache": {"hit": False, "ttl_seconds": OPTION_CHAIN_CACHE_TTL_SECONDS},
        "upstream": {
            "quotes": "timeout" if "quotes" in timed_out else "received",
            "greeks": "timeout" if "greeks" in timed_out else "received",
            "timed_out": timed_out,
            "timeout_seconds": OPTION_CHAIN_UPSTREAM_TIMEOUT_SECONDS,
        },
        "request_elapsed_ms": elapsed_ms,
    }
    if timed_out:
        payload["status"] = "WAIT"
        payload["reason"] = "Upstream timeout; missing option-chain fields are unavailable and cannot qualify a trade."
    elif not output:
        payload["status"] = "WAIT"
        payload["reason"] = "No complete live option quotes were received."
    # Cache only complete quote responses; never cache timeout/partial data.
    if not timed_out and output and OPTION_CHAIN_CACHE_TTL_SECONDS > 0:
        _option_chain_cache[index] = (time.monotonic(), payload)
    return payload


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


def _refresh_signals_worker() -> None:
    global _signal_build_metrics, _signal_cache
    started = time.monotonic()
    error_text = None
    try:
        _get_signals_uncached(force=True)
    except Exception as exc:
        error_text = f"{type(exc).__name__}: signal refresh failed"
        logger.warning("SIGNAL_REFRESH_FAILED: %s", type(exc).__name__)
    finally:
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        with _lock:
            _signal_build_metrics["last_duration_ms"] = elapsed_ms
            _signal_build_metrics["build_count"] = int(_signal_build_metrics.get("build_count", 0)) + 1
            _signal_build_metrics["last_error"] = error_text
            _signal_build_metrics["in_flight"] = False
            if _signal_cache is not None:
                _signal_cache["performance"] = {
                    "signal_build_ms": elapsed_ms,
                    "signal_build_count": _signal_build_metrics["build_count"],
                    "single_flight": True,
                    "background_refresh": True,
                }


def _stale_signal_snapshot(cached: dict[str, Any], age_seconds: float | None) -> dict[str, Any]:
    # JSON round-trip makes a detached copy so stale flags never mutate the cache.
    snapshot = json.loads(json.dumps(cached, default=str))
    actionable_keys = {
        "strike", "expiry", "entry", "entry_price", "entry_price_ltp",
        "exit", "exit_price", "stop_loss", "stop_loss_price", "sl",
        "target", "target_price", "take_profit", "trigger_price",
        "limit_price", "order_type", "quantity", "qty", "lots",
        "contract_token", "option_type", "option_side",
    }
    active_decisions = {
        "CALL BUY", "PUT BUY", "BUY", "SELL", "CE BUY", "PE BUY",
        "BUY CE", "BUY PE", "BUY CALL", "BUY PUT", "LONG", "SHORT",
    }

    def sanitize_stale_payload(value: Any) -> Any:
        if isinstance(value, list):
            return [sanitize_stale_payload(item) for item in value]
        if not isinstance(value, dict):
            return value
        row = {key: sanitize_stale_payload(child) for key, child in value.items()}
        for key in list(row):
            if str(key).lower() in actionable_keys:
                row[key] = None
        decision = str(row.get("decision") or "").strip().upper()
        if decision in active_decisions:
            row["candidate_decision"] = row.get("candidate_decision") or decision
            row["decision"] = "WAIT"
        if "data_fresh" in row:
            row["data_fresh"] = False
        if "live" in row:
            row["live"] = False
        return row

    snapshot["live"] = False
    snapshot["refreshing"] = True
    snapshot["cache_age_seconds"] = round(age_seconds, 1) if age_seconds is not None else None
    snapshot["feed"] = {**(snapshot.get("feed") or {}), "connected": False, "mode": "CACHED_REFRESHING"}
    for row in (snapshot.get("market") or {}).values():
        if isinstance(row, dict):
            row["live"] = False
            row["cached"] = True
            row["feed_mode"] = "CACHED_REFRESHING"
            if isinstance(row.get("option_chain"), list):
                row["option_chain"] = [
                    {**item, "live": False, "cached": True, "freshness": "STALE"}
                    for item in row["option_chain"] if isinstance(item, dict)
                ]
    for row in (snapshot.get("signals") or {}).values():
        if not isinstance(row, dict):
            continue
        decision = str(row.get("decision") or "WAIT").upper()
        if decision in active_decisions:
            row["candidate_decision"] = row.get("candidate_decision") or decision
        row["decision"] = "WAIT"
        row["data_fresh"] = False
        row["live"] = False
        row["cached"] = True
        row["feed_mode"] = "CACHED_REFRESHING"
        sanitized = sanitize_stale_payload(row)
        row.clear()
        row.update(sanitized)
        row["decision"] = "WAIT"
        row["data_fresh"] = False
        row["live"] = False
        row["cached"] = True
        row["feed_mode"] = "CACHED_REFRESHING"
        trade_plan = dict(row.get("trade_plan") or {})
        trade_plan.update({
            "selection_grade": "WAIT", "strike": None, "expiry": None,
            "entry": None, "exit": None, "stop_loss": None, "target": None,
            "signal_only": True, "data_fresh": False, "decision": "WAIT",
        })
        row["trade_plan"] = trade_plan
        for engine_key in ("five_layer_engine", "quant_engine"):
            engine_payload = row.get(engine_key)
            if isinstance(engine_payload, dict):
                engine_payload["decision"] = "WAIT"
                engine_payload["data_fresh"] = False
                row[engine_key] = engine_payload
        strategy_filter = dict(row.get("strategy_filter") or {})
        if strategy_filter:
            strategy_filter.update({
                "pass": False, "state": "BLOCKED_BY_STALE_DATA",
                "reason": "Signal refresh is in progress; stale market data cannot authorize a trade.",
            })
            row["strategy_filter"] = strategy_filter
            trade_plan["strategy_filter"] = strategy_filter
            row["trade_plan"] = trade_plan
        stability = dict(row.get("signal_stability") or {})
        stability["state"] = "BLOCKED_BY_STALE_DATA"
        row["signal_stability"] = stability
        validation = dict(row.get("live_validation") or {})
        validation["decision"] = "WAIT"
        validation["verdict"] = "WARN"
        blocks = list(validation.get("blocks") or [])
        if not any("cached data is not actionable" in str(block).lower() for block in blocks):
            blocks.append("Signal refresh is in progress; cached data is not actionable.")
        validation["blocks"] = blocks
        row["live_validation"] = validation

    stale_commodities = []
    for raw in (snapshot.get("commodities") or []):
        if not isinstance(raw, dict):
            continue
        row = sanitize_stale_payload(raw)
        decision = str(row.get("decision") or "WAIT").upper()
        if decision in active_decisions:
            row["candidate_decision"] = row.get("candidate_decision") or decision
        row.update({
            "decision": "WAIT",
            "data_fresh": False,
            "live": False,
            "cached": True,
            "feed_mode": "CACHED_REFRESHING",
            "signal_stability": {"state": "BLOCKED_BY_STALE_DATA"},
        })
        stale_commodities.append(row)
    if "commodities" in snapshot:
        snapshot["commodities"] = stale_commodities

    snapshot["trade_plans"] = []
    snapshot["qualified_trade_count"] = 0
    snapshot["message"] = "Showing cached quotes as stale while the broker snapshot refreshes in the background."
    return snapshot

def _get_signals(force: bool = False) -> dict[str, Any]:
    """Serve immediately and refresh expired market snapshots in a single background worker."""
    global _signal_build_metrics
    with _lock:
        age = time.monotonic() - _signal_cache_at if _signal_cache is not None else None
        fresh = _signal_cache is not None and age is not None and age < SIGNAL_CACHE_SECONDS
        if fresh and not force:
            return _signal_cache
        cached = _signal_cache
        start_refresh = not bool(_signal_build_metrics.get("in_flight"))
        if start_refresh:
            _signal_build_metrics["in_flight"] = True
    if start_refresh:
        worker = threading.Thread(target=_refresh_signals_worker, name="signal-refresh", daemon=True)
        worker.start()
    if cached is not None:
        return _stale_signal_snapshot(cached, age)
    payload = _empty_payload("Initial Angel One snapshot is loading in the background; retry shortly.")
    payload["refreshing"] = True
    payload["performance"] = {"signal_build_ms": _signal_build_metrics.get("last_duration_ms"), "in_flight": True}
    return payload

def _get_signals_uncached(force: bool = False) -> dict[str, Any]:
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
        # Batch all index spot tokens by exchange once instead of issuing one
        # REST quote request per index before the candle/options pipeline.
        spot_quotes: dict[str, dict[str, Any]] = {}
        spot_contracts: dict[str, dict[str, Any]] = {}
        for index in INDEXES:
            try:
                spot_contracts[index] = _find_index_contract(rows, index)
            except Exception:
                continue
        by_exchange: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for index, contract in spot_contracts.items():
            by_exchange.setdefault(str(contract["exchange"]), []).append((index, contract))
        for exchange, contracts in by_exchange.items():
            try:
                batch = _quotes(adapter, exchange, [str(contract["token"]) for _, contract in contracts])
                for index, contract in contracts:
                    quote = batch.get(str(contract["token"]))
                    if quote is not None:
                        spot_quotes[index] = quote
            except Exception:
                # Each index has a single-token fallback inside _index_snapshot.
                continue
        for index in INDEXES:
            index_started = time.perf_counter()
            try:
                result, quote = _index_snapshot(adapter, rows, index, spot_quote=spot_quotes.get(index))
                elapsed_index_ms = round((time.perf_counter() - index_started) * 1000, 2)
                result["performance"] = {**dict(result.get("performance") or {}), "index_snapshot_ms": elapsed_index_ms}
                quote["performance"] = {"index_snapshot_ms": elapsed_index_ms}
                signals[index] = result
                market[index] = quote
            except Exception as exc:
                # Keep independently verified spot data visible even if the
                # heavier signal pipeline fails (e.g. insufficient candles,
                # option Greeks or option ATR). A signal failure must not blank
                # the Market/Dashboard pages or silently become an actionable trade.
                reason = str(exc)[:220]
                elapsed_index_ms = round((time.perf_counter() - index_started) * 1000, 2)
                signals[index] = _wait_signal(index, reason)
                signals[index]["performance"] = {"index_snapshot_ms": elapsed_index_ms, "five_layer_validation_ms": None}
                market_row: dict[str, Any] = {
                    "ltp": None, "age_seconds": None, "feed_mode": "DATA_ERROR",
                    "performance": {"index_snapshot_ms": elapsed_index_ms},
                    "source": "angelone_smartapi", "live": False,
                    "error": reason, "signal_error": reason, "option_chain": [],
                }
                try:
                    index_config = INDEXES[index]
                    fallback_quotes = _quotes(adapter, index_config["exchange"], [str(index_config["token"])])
                    spot_fallback = fallback_quotes.get(str(index_config["token"]))
                    if spot_fallback is None:
                        spot_fallback = next((value for key, value in fallback_quotes.items() if str(key) == str(index_config["token"])), None)
                    if spot_fallback:
                        spot_ltp = _number(spot_fallback.get("ltp"))
                        spot_timestamp = _quote_timestamp(spot_fallback)
                        parsed_spot_timestamp = datetime.fromisoformat(_iso(spot_timestamp)) if spot_timestamp and _iso(spot_timestamp) else None
                        spot_age = (_utc_now() - parsed_spot_timestamp).total_seconds() if parsed_spot_timestamp else None
                        spot_live = spot_ltp is not None and spot_ltp > 0 and spot_age is not None and 0 <= spot_age <= 60 and _is_market_session_open(index)
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
                            chart_1h_rows = _aggregate_hourly_chart_rows(chart_rows)
                            chart_1d_rows: list[dict[str, Any]] = []
                            try:
                                daily_end_dt = datetime.now(IST)
                                daily_start_text = (daily_end_dt - timedelta(days=45)).strftime("%Y-%m-%d %H:%M")
                                daily_end_text = daily_end_dt.strftime("%Y-%m-%d %H:%M")
                                daily_payload = adapter.candles(
                                    index_config["exchange"], index_config["token"], "ONE_DAY",
                                    daily_start_text, daily_end_text,
                                )
                                for daily_candle in daily_payload.get("candles") or []:
                                    if not isinstance(daily_candle, (list, tuple)) or len(daily_candle) < 6:
                                        continue
                                    daily_stamp = _iso(daily_candle[0])
                                    daily_dt = datetime.fromisoformat(daily_stamp) if daily_stamp else None
                                    values = [_number(daily_candle[pos]) for pos in (1, 2, 3, 4)]
                                    if daily_dt is None or any(value is None for value in values):
                                        continue
                                    chart_1d_rows.append({
                                        "t": int(daily_dt.timestamp()), "timestamp": daily_stamp,
                                        "open": values[0], "high": values[1], "low": values[2], "close": values[3],
                                        "volume": _number(daily_candle[5]),
                                    })
                            except Exception:
                                # Missing daily history is a visible empty timeframe, never fabricated.
                                chart_1d_rows = []
                            chart_1d_rows = chart_1d_rows[-45:]
                            chart_1w_rows = _aggregate_weekly_chart_rows(chart_1d_rows)
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
                            market_row["timeframes"] = {"1m": [], "5m": chart_rows, "15m": chart_15m_rows, "1H": chart_1h_rows, "1D": chart_1d_rows, "1W": chart_1w_rows}
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
            and _commodity_contract_matches(row, name)
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
            live = ltp is not None and ltp > 0 and age is not None and 0 <= age <= 60 and _is_market_session_open(name)
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


def _provider_config_fingerprint(provider: str) -> str:
    """Fingerprint key/model/endpoint configuration without exposing secrets."""
    if provider == "nvidia":
        values = (
            os.getenv("NVIDIA_API_KEY") or "",
            os.getenv("NVIDIA_CHAT_MODEL", "z-ai/glm-5.3"),
            os.getenv("NVIDIA_CHAT_FALLBACK_MODEL", "qwen/qwen2.5-coder-32b-instruct"),
            os.getenv("NVIDIA_CHAT_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
        )
    elif provider == "openrouter":
        values = (
            os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY") or "",
            os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"),
            os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"),
        )
    else:
        raise ValueError("Unsupported AI provider")
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode("utf-8")).hexdigest()


@app.get("/v1/ai/status")
def ai_status(_: str = Depends(_device)) -> dict[str, Any]:
    # NVIDIA is primary; OpenRouter is an optional fallback.
    providers = [
        ("nvidia", ("NVIDIA_API_KEY",), os.getenv("NVIDIA_CHAT_MODEL", "z-ai/glm-5.3")),
        ("openrouter", ("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY"), os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")),
    ]
    selected = next((item for item in providers if _provider_key_present(*item[1])), None)
    provider_status = {
        name: {
            "configured": _provider_key_present(*env_names),
            "status": "configured_not_tested" if _provider_key_present(*env_names) else "not_configured",
            "model": model_name,
            "ok": False,
        }
        for name, env_names, model_name in providers
    }
    with _lock:
        for name in ("nvidia", "openrouter"):
            cached = _ai_provider_test_cache.get(name)
            if (
                cached
                and cached.get("configured") == provider_status[name]["configured"]
                and cached.get("_config_fingerprint") == _provider_config_fingerprint(name)
            ):
                provider_status[name] = {
                    key: value for key, value in cached.items() if key != "_config_fingerprint"
                }
    return {
        "provider": selected[0] if selected else "deterministic_fallback",
        "model": selected[2] if selected else "five-layer-quant-context",
        "status": "configured" if selected else "fallback_ready",
        "llm_configured": selected is not None,
        "providers": provider_status,
        "message": "Cloud model key detected; connectivity is tested separately." if selected else "No supported LLM key is configured. Chat can still report actual market fields and deterministic risk gates; it will not pretend an LLM answered.",
        "signal_only": True,
    }


def _run_ai_validation_probe(provider: str, api_key: str, model: str, endpoint: str, market_row: dict[str, Any]) -> dict[str, Any]:
    """Perform one real authenticated model call and capture a bounded, secret-free result."""
    started = time.perf_counter()
    source_payload = {
        "source": market_row.get("source"),
        "source_timestamp": market_row.get("source_timestamp") or market_row.get("timestamp"),
        "ltp": market_row.get("ltp"),
        "age_seconds": market_row.get("age_seconds"),
        "live": market_row.get("live") is True,
    }
    prompt = (
        "Validate this market snapshot only as a secondary reviewer. Never invent missing facts. "
        "Return one JSON object with keys verdict (PASS or WAIT) and reason. PASS only if source is "
        "angelone_smartapi, source_timestamp exists, ltp is a positive number, age_seconds is numeric "
        "between 0 and 60, and live is true. Otherwise verdict must be WAIT. This AI result cannot "
        "override deterministic risk gates. Snapshot: " + json.dumps(source_payload, separators=(",", ":"))
    )
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "max_tokens": 100,
        "messages": [
            {"role": "system", "content": "You are a cautious market-data validation assistant. Output JSON only."},
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/sparmar3786-pixel/AI-TRADING"
        headers["X-Title"] = "AI-TRADING Data Validator"
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        data = _provider_json_with_retry(request, timeout=8, provider=provider)
        choices = data.get("choices") or []
        output = str(((choices[0].get("message") or {}).get("content") if choices else "") or "").strip()
        # Parse the model's verdict if possible; malformed output is WAIT, never PASS.
        verdict = "WAIT"
        reason = "Model did not return a parseable validation verdict."
        try:
            cleaned = output.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(cleaned)
            candidate = str(parsed.get("verdict", "WAIT")).upper()
            verdict = "PASS" if candidate == "PASS" and source_payload["live"] and source_payload["source_timestamp"] and isinstance(source_payload["ltp"], (int, float)) and source_payload["ltp"] > 0 and isinstance(source_payload["age_seconds"], (int, float)) and 0 <= source_payload["age_seconds"] <= 60 else "WAIT"
            reason = str(parsed.get("reason") or "")[:180]
        except (ValueError, TypeError, AttributeError):
            reason = output[:180] or reason
        return {
            "provider": provider, "configured": True, "ok": bool(output),
            "status": "ok" if output else "empty_model_response",
            "model": model, "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "verdict": verdict, "reason": reason, "output": output[:240],
        }
    except urllib.error.HTTPError as exc:
        # Never echo provider response bodies; they may contain account details.
        # Rate limits are actionable and should not be misreported as malformed JSON.
        retry_after = (exc.headers.get("Retry-After") if exc.headers else None)
        rate_limited = exc.code == 429
        return {"provider": provider, "configured": True, "ok": False,
                "status": "rate_limited" if rate_limited else "http_error",
                "model": model, "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "verdict": "WAIT",
                "retry_after_seconds": retry_after if retry_after and retry_after.isdigit() else None,
                "error": "Provider access rate exceeded; retry after the provider's cooldown." if rate_limited else f"Provider returned HTTP {exc.code}."}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"provider": provider, "configured": True, "ok": False, "status": "connection_error",
                "model": model, "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "verdict": "WAIT", "error": f"Provider request failed ({type(exc).__name__})."}


@app.post("/v1/ai/validate")
def ai_validate_snapshot(body: dict[str, Any], _: str = Depends(_device)) -> dict[str, Any]:
    """Return provider configuration and deterministic market-data eligibility without inventing an AI pass."""
    payload = _get_signals(force=False)
    index = str(body.get("index") or "NIFTY").strip().upper()
    market_row = dict((payload.get("market") or {}).get(index) or {})
    signal_row = dict((payload.get("signals") or {}).get(index) or {})
    timestamp = _iso(market_row.get("source_timestamp") or market_row.get("timestamp"))
    parsed = datetime.fromisoformat(timestamp) if timestamp else None
    age = (_utc_now() - parsed).total_seconds() if parsed else None
    fresh = (
        market_row.get("source") == "angelone_smartapi"
        and _number(market_row.get("ltp")) is not None
        and (_number(market_row.get("ltp")) or 0) > 0
        and age is not None and 0 <= age <= 60
    )
    providers: dict[str, Any] = {}
    for provider, env_names in (
        ("nvidia", ("NVIDIA_API_KEY",)),
        ("openrouter", ("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY")),
    ):
        configured = any(os.getenv(name, "").strip() for name in env_names)
        providers[provider] = {
            "configured": configured,
            "ok": False,
            "status": "not_configured" if not configured else "configured_not_tested",
            "verdict": "WAIT",
        }
    return {
        "overall_status": "BLOCKED_NO_LIVE_DATA" if not fresh else "PROVIDER_TEST_REQUIRED",
        "deterministic_decision": str(signal_row.get("decision") or "WAIT") if fresh else "WAIT",
        "providers": providers,
        "market_snapshot_available": fresh,
        "source_timestamp": timestamp,
        "age_seconds": round(age, 2) if age is not None else None,
        "signal_only": True,
        "order_placement_enabled": False,
    }


@app.post("/v1/providers/ai/test")
def test_ai_providers(_: str = Depends(_device)) -> dict[str, Any]:
    # A test call is deliberately explicit/on-demand, not added to every market tick.
    # It validates a real broker snapshot when one is cached; no sample price is sent.
    market_row = dict(((_signal_cache or {}).get("market") or {}).get("NIFTY") or {})
    source_stamp = _iso(market_row.get("source_timestamp") or market_row.get("timestamp"))
    parsed_stamp = datetime.fromisoformat(source_stamp) if source_stamp else None
    actual_age = (_utc_now() - parsed_stamp).total_seconds() if parsed_stamp else None
    market_row["age_seconds"] = round(actual_age, 2) if actual_age is not None else None
    market_row["live"] = (
        market_row.get("source") == "angelone_smartapi"
        and _number(market_row.get("ltp")) is not None
        and (_number(market_row.get("ltp")) or 0) > 0
        and actual_age is not None and 0 <= actual_age <= 60
    )
    checks: list[dict[str, Any]] = []
    nvidia_key = (os.getenv("NVIDIA_API_KEY") or "").strip()
    nvidia_model = os.getenv("NVIDIA_CHAT_MODEL", "z-ai/glm-5.3").strip()
    if nvidia_key:
        try:
            probe = _run_openai_compatible_completion(
                nvidia_key, nvidia_model, [
                    {"role": "system", "content": "You are a connectivity probe. Reply with the exact text NVIDIA_OK."},
                    {"role": "user", "content": "Reply with NVIDIA_OK only."},
                ],
                provider="nvidia",
                endpoint=os.getenv("NVIDIA_CHAT_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions").strip(),
            )
            checks.append({"provider": "nvidia", "configured": True, "ok": True, "status": "ok",
                           "model": probe.get("model"), "latency_ms": probe.get("latency_ms"),
                           "verdict": "WAIT", "message": "NVIDIA authenticated and returned a real chat response."})
        except RuntimeError as exc:
            checks.append({"provider": "nvidia", "configured": True, "ok": False, "status": str(exc)[:80],
                           "model": nvidia_model, "verdict": "WAIT"})
    else:
        checks.append({"provider": "nvidia", "configured": False, "ok": False,
                       "status": "not_configured", "verdict": "WAIT"})
    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY") or "").strip()
    if openrouter_key:
        checks.append(_run_ai_validation_probe(
            "openrouter", openrouter_key, os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct").strip(),
            "https://openrouter.ai/api/v1/chat/completions", market_row))
    else:
        checks.append({"provider": "openrouter", "configured": False, "ok": False, "status": "not_configured", "verdict": "WAIT"})
    tested = [item for item in checks if item.get("provider") in ("nvidia", "openrouter")]
    with _lock:
        for item in tested:
            cached_item = dict(item)
            cached_item["_config_fingerprint"] = _provider_config_fingerprint(str(item["provider"]))
            _ai_provider_test_cache[item["provider"]] = cached_item
    succeeded = [item for item in tested if item.get("ok") is True]
    return {
        "status": "ok" if succeeded else ("not_configured" if not any(item.get("configured") for item in tested) else "failed"),
        "checks": checks, "providers": {item["provider"]: item for item in checks},
        "market_snapshot_available": bool(market_row.get("source_timestamp") and market_row.get("ltp") is not None),
        "message": "At least one configured provider returned a real response. AI cannot override deterministic risk gates."
            if succeeded else "No configured AI provider passed its real request. Inspect each provider status and Railway variables.",
        "signal_only": True, "order_placement_enabled": False,
    }

@app.post("/v1/ai/review-signal")
def review_signal_with_nvidia(payload: dict[str, Any], _: str = Depends(_device)) -> dict[str, Any]:
    """Use NVIDIA first and OpenRouter as fallback; neither can override deterministic risk gates."""
    index = str(payload.get("index") or "").strip().upper()
    if index not in INDEXES:
        return {"provider": "none", "ok": False, "verdict": "WAIT", "decision": "WAIT", "status": "invalid_index", "reason": "Index is not supported."}
    snapshot = dict(_signal_cache or {})
    signal_map = dict(snapshot.get("signals") or {})
    market_map = dict(snapshot.get("market") or {})
    signal = dict(signal_map.get(index) or {})
    market = dict(market_map.get(index) or {})
    validation = dict(signal.get("live_validation") or {})
    checks = dict(validation.get("checks") or {})
    expected = str(signal.get("decision") or "WAIT").upper()
    if expected not in ("CALL BUY", "PUT BUY") or validation.get("verdict") != "PASS" or not checks or not all(value is True for value in checks.values()):
        return {
            "provider": "none", "configured": False, "ok": False, "verdict": "WAIT", "decision": "WAIT",
            "status": "deterministic_gate_blocked",
            "reason": "The backend five-layer checks are not all PASS; cloud AI cannot override them.",
            "blocks": list(validation.get("blocks") or ["DETERMINISTIC_VALIDATION_NOT_PASS"]),
            "checks": {"backend_validation": False, "ai_direction_consistent": False},
            "signal_only": True, "order_placement_enabled": False,
        }
    providers: list[tuple[str, str, str]] = []
    nvidia_key = (os.getenv("NVIDIA_API_KEY") or "").strip()
    if nvidia_key:
        providers.append(("nvidia", nvidia_key, os.getenv("NVIDIA_CHAT_MODEL", "z-ai/glm-5.3").strip()))
    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY") or "").strip()
    if openrouter_key:
        providers.append(("openrouter", openrouter_key, os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct").strip()))
    if not providers:
        return {
            "provider": "none", "configured": False, "ok": False, "verdict": "WAIT",
            "decision": "WAIT", "status": "not_configured",
            "reason": "Configure NVIDIA_API_KEY for NVIDIA chat and/or OPENROUTER_API_KEY on the backend. KUMO_NVIDIA_API_KEY is reserved for Kumo Tabular inference.",
            "blocks": ["AI_PROVIDER_NOT_CONFIGURED"],
            "checks": {"backend_validation": True, "ai_direction_consistent": False},
            "signal_only": True, "order_placement_enabled": False,
        }
    review_input = {
        "index": index, "candidate_decision": expected,
        "market": {key: market.get(key) for key in ("ltp", "source", "source_timestamp", "timestamp", "age_seconds", "live")},
        "signal": {key: signal.get(key) for key in ("decision", "strike", "option_side", "entry", "stop_loss", "target", "data_fresh")},
        "strategy_suite": signal.get("strategy_suite"),
        "live_validation": validation,
    }
    messages = [
        {"role": "system", "content": "You are a strict independent trading risk reviewer. Read only the supplied JSON. Return ONLY JSON with keys verdict (PASS or WAIT), decision (CALL BUY, PUT BUY, or WAIT), conflicting_direction (boolean), reason (string). Return PASS only when the provided deterministic checks are all true and the candidate has no missing/stale data, invalid quote, conflicting direction, invalid stop loss/target, or failed risk gate. If uncertain return WAIT. Do not invent prices. Confidence is not profit probability."},
        {"role": "user", "content": json.dumps(review_input, separators=(",", ":"), default=str)[:10000]},
    ]
    failures: list[dict[str, str]] = []
    for provider, api_key, model in providers:
        try:
            if provider == "nvidia":
                result = _run_openai_compatible_completion(
                    api_key, model, messages, provider="nvidia",
                    endpoint=os.getenv("NVIDIA_CHAT_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions").strip(),
                )
            else:
                result = _run_openai_compatible_completion(
                    api_key, model, messages, provider="openrouter",
                    endpoint=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions").strip(),
                )
            text_response = str(result.get("answer") or "").strip()
            match = re.search(r"\{.*\}", text_response, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else {}
            ai_decision = str(parsed.get("decision") or "WAIT").strip().upper()
            ai_verdict = str(parsed.get("verdict") or "WAIT").strip().upper()
            conflict = parsed.get("conflicting_direction") is True or ai_decision != expected
            passed = ai_verdict == "PASS" and ai_decision == expected and not conflict
            return {
                "provider": provider, "configured": True, "ok": True, "status": "ok",
                "model": result.get("model"), "latency_ms": result.get("latency_ms"),
                "verdict": "PASS" if passed else "WAIT", "decision": expected if passed else "WAIT",
                "ai_decision": ai_decision, "ai_direction_consistent": not conflict,
                "reason": str(parsed.get("reason") or f"{provider} did not confirm every risk condition.")[:500],
                "blocks": [] if passed else [f"{provider.upper()}_REVIEW_NOT_PASS"],
                "checks": {"backend_validation": True, "ai_direction_consistent": not conflict, "ai_verdict_pass": ai_verdict == "PASS"},
                "provider_failures": failures,
                "signal_only": True, "order_placement_enabled": False,
            }
        except (RuntimeError, ValueError, TypeError) as exc:
            failures.append({"provider": provider, "status": str(exc)[:100]})
    return {
        "provider": "none", "configured": True, "ok": False, "verdict": "WAIT",
        "decision": "WAIT", "status": "all_providers_failed",
        "reason": "NVIDIA and OpenRouter review failed or returned invalid JSON.",
        "provider_failures": failures,
        "blocks": ["AI_REVIEW_FAILED"],
        "checks": {"backend_validation": True, "ai_direction_consistent": False},
        "signal_only": True, "order_placement_enabled": False,
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
    # Force a fresh network probe: cached headlines must never make a broken
    # provider appear green after its key was revoked or its quota was exhausted.
    evidence = fetch_market_news_sentiment(
        "NIFTY", exa_api_key=os.getenv("EXA_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY"), force=True,
    )
    provider_checks = dict(evidence.get("provider_checks") or {})
    checks = []
    for name, configured in (("exa", exa), ("tavily", tavily)):
        observed = dict(provider_checks.get(name) or {})
        checks.append({
            "provider": name, "configured": configured,
            "ok": configured and observed.get("ok") is True,
            "status": observed.get("status", "not_configured" if not configured else "test_failed"),
            "result_count": observed.get("result_count", 0),
            "error": observed.get("error"),
        })
    articles = list(evidence.get("articles") or [])
    configured_checks = [item for item in checks if item["configured"]]
    passed = [item for item in configured_checks if item["ok"]]
    return {
        "status": "ok" if passed else ("not_configured" if not configured_checks else "failed"),
        "checks": checks, "providers": {item["provider"]: item for item in checks},
        "evidence_count": len(articles), "search_evidence": articles[:8],
        "errors": evidence.get("errors", []),
        "message": "Provider authentication and search request succeeded." if passed else "No configured search provider passed a live request. Inspect each provider's status; secrets are never returned.",
    }


def _run_chat_completion(provider: str, api_key: str, model: str, endpoint: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    """Make a real server-side LLM call. Never expose keys or raw provider bodies."""
    started = time.perf_counter()
    body = json.dumps({
        "model": model, "temperature": 0.2, "max_tokens": 700,
        "messages": messages,
    }).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/sparmar3786-pixel/AI-TRADING"
        headers["X-Title"] = "AI-TRADING Market Assistant"
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=14) as response:
            data = json.loads(response.read().decode("utf-8"))
        choices = data.get("choices") or []
        answer = str(((choices[0].get("message") or {}).get("content") if choices else "") or "").strip()
        if not answer:
            raise RuntimeError("empty_response")
        return {
            "answer": answer, "provider": provider, "model": model, "llm_used": True,
            "status": "connected", "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError(f"{provider}_rate_limited") from None
        if exc.code in (401, 403):
            raise RuntimeError(f"{provider}_authentication_failed") from None
        raise RuntimeError(f"{provider}_http_{exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"{provider}_{type(exc).__name__.lower()}") from None


def _provider_json_with_retry(request: urllib.request.Request, *, timeout: float, provider: str) -> dict[str, Any]:
    """Retry one transient transport/5xx or empty-body response without retrying auth/quota errors."""
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            choices = data.get("choices") or []
            answer = str(((choices[0].get("message") or {}).get("content") if choices else "") or "").strip()
            if answer or attempt == 1:
                return data
            last_error = RuntimeError(f"{provider}_empty_response")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if attempt == 1 or exc.code not in (502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if attempt == 1:
                raise
        time.sleep(0.25)
    if last_error:
        raise last_error
    raise RuntimeError(f"{provider}_request_failed")


def _run_openai_compatible_completion_once(
    api_key: str, model: str, messages: list[dict[str, str]], *,
    provider: str, endpoint: str, referer: str | None = None,
) -> dict[str, Any]:
    """Call an OpenAI-compatible chat endpoint without leaking credentials."""
    started = time.perf_counter()
    safe_model = (model or "").strip()
    if not safe_model:
        raise RuntimeError(f"{provider}_model_not_configured")
    payload = {
        "model": safe_model,
        "messages": [{"role": str(m.get("role")), "content": str(m.get("content") or "")[:12000]}
                     for m in messages if m.get("role") in ("system", "user", "assistant")],
        "temperature": 0.2,
        "max_tokens": 900,
    }
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = referer or "https://github.com/sparmar3786-pixel/AI-TRADING"
        headers["X-Title"] = "AI-TRADING"
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        data = _provider_json_with_retry(request, timeout=22, provider=provider)
        choices = data.get("choices") or []
        message = (choices[0].get("message") or {}) if choices else {}
        answer = str(message.get("content") or "").strip()
        if not answer:
            raise RuntimeError(f"{provider}_empty_response")
        return {"answer": answer, "provider": provider, "model": safe_model,
                "llm_used": True, "ok": True, "status": "connected",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError(f"{provider}_rate_limited") from None
        if exc.code in (401, 403):
            raise RuntimeError(f"{provider}_authentication_failed") from None
        raise RuntimeError(f"{provider}_http_{exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"{provider}_{type(exc).__name__.lower()}") from None


def _run_openai_compatible_completion(
    api_key: str, model: str, messages: list[dict[str, str]], *,
    provider: str, endpoint: str, referer: str | None = None,
) -> dict[str, Any]:
    """Try the primary NVIDIA model first, then a configured NVIDIA fallback."""
    candidates = [model]
    if provider == "nvidia":
        fallback_model = os.getenv(
            "NVIDIA_CHAT_FALLBACK_MODEL", "qwen/qwen2.5-coder-32b-instruct"
        ).strip()
        if fallback_model and fallback_model not in candidates:
            candidates.append(fallback_model)
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            result = _run_openai_compatible_completion_once(
                api_key, candidate, messages, provider=provider,
                endpoint=endpoint, referer=referer,
            )
            if candidate != model:
                result["fallback_used"] = True
                result["primary_model"] = model
            return result
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{provider}_model_not_configured")


@app.post("/v1/ai/chat")
@app.post("/v1/ai/nvidia-chat")
def ai_chat(body: dict[str, Any], _: str = Depends(_device)) -> dict[str, Any]:
    """Use a real cloud provider when configured; disclose fallback if every provider fails."""
    index = str(body.get("index") or "NIFTY").strip().upper()
    is_commodity = index in COMMODITY_NAMES
    if index not in INDEXES and not is_commodity:
        raise HTTPException(status_code=400, detail="Unsupported index or MCX commodity.")
    question = str(body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="A question is required.")
    try:
        payload = _get_signals()
        if is_commodity:
            commodity_rows = payload.get("commodities") if isinstance(payload.get("commodities"), list) else []
            market = next(
                (dict(row) for row in commodity_rows if isinstance(row, dict)
                 and str(row.get("name") or row.get("symbol") or "").strip().upper() == index),
                {"name": index, "symbol": index, "source": "angelone_smartapi", "live": False, "ltp": None, "status": "WAIT"},
            )
            signal = dict(market)
        else:
            market = dict((payload.get("market") or {}).get(index) or {})
            signal = dict((payload.get("signals") or {}).get(index) or {})
        news = dict(signal.get("news_sentiment") or cached_market_news_sentiment(index))
        validation = dict(signal.get("live_validation") or {})
        reasons = signal.get("reasons") or signal.get("reason") or []
        if not isinstance(reasons, list):
            reasons = [str(reasons)]
        context = {
            "index": index, "market": market, "signal": signal, "validation": validation,
            "search_evidence": list(news.get("articles") or [])[:6],
            "live_data_status": "fresh only if market.live=true and source_timestamp is recent",
        }
        system_message = (
            "You are AI-TRADING's secondary market research assistant. Answer the user's latest question "
            "directly and specifically; do not repeat a previous answer or a generic market summary unless "
            "the latest question asks for it. Use conversation history only for context, not as a template. "
            "If the latest question differs from the previous turn, address the new request first. "
            "Use only supplied evidence; never invent prices, OI, Greeks, volume, candle history, "
            "support/resistance or timestamps. Clearly label unavailable/stale data and distinguish facts "
            "from hypotheses. Explain signal and risk gates, but never override a deterministic WAIT/REJECT. "
            "This backend is read-only and does not place orders."
        )
        history = body.get("history") if isinstance(body.get("history"), list) else []
        messages = [{"role": "system", "content": system_message},
                    {"role": "user", "content": "Verified context JSON:\n" + json.dumps(context, separators=(",", ":"), default=str)[:14000]}]
        for item in history[-8:]:
            if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
                continue
            content = str(item.get("content") or "").strip()
            if content:
                messages.append({"role": str(item["role"]), "content": content[:3000]})
        messages.append({"role": "user", "content": question[:3000]})
        # Try every configured provider in deterministic order. Configuration alone is
        # not success: each provider must return a real inference response.
        failures: list[dict[str, str]] = []
        providers = [
            ("nvidia", (os.getenv("NVIDIA_API_KEY") or "").strip()),
            ("openrouter", (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY") or "").strip()),
        ]
        for provider, api_key in providers:
            if not api_key:
                failures.append({"provider": provider, "status": "not_configured"})
                continue
            try:
                if provider == "nvidia":
                    result = _run_openai_compatible_completion(
                        api_key, os.getenv("NVIDIA_CHAT_MODEL", "z-ai/glm-5.3").strip(), messages,
                        provider="nvidia",
                        endpoint=os.getenv("NVIDIA_CHAT_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions").strip(),
                    )
                else:
                    result = _run_openai_compatible_completion(
                        api_key, os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct").strip(), messages,
                        provider="openrouter",
                        endpoint=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions").strip(),
                    )
                suite = dict(market.get("strategy_suite") or signal.get("strategy_suite") or {})
                suite_trace = dict(suite.get("trace") or {})
                suite_trace["ai_context_sent"] = bool(suite)
                suite_trace["ai_semantic_use_verifiable"] = False
                suite_trace["ai_provider"] = provider if suite else None
                suite_trace["ai_model"] = result.get("model") if suite else None
                suite_trace["ai_context_status"] = (
                    "STRATEGY_OUTPUT_INCLUDED_IN_PROMPT_CONTEXT"
                    if suite else "STRATEGY_OUTPUT_NOT_AVAILABLE"
                )
                return {
                    **result, "index": index, "question": question,
                    "market": market, "signal": signal, "validation": validation,
                    "strategy_consumption_trace": suite_trace,
                    "search_attempted": bool(os.getenv("EXA_API_KEY", "").strip() or os.getenv("TAVILY_API_KEY", "").strip()),
                    "search_evidence": list(news.get("articles") or [])[:8],
                    "provider_failures": failures, "signal_only": True,
                    "order_placement_enabled": False,
                }
            except RuntimeError as exc:
                failures.append({"provider": provider, "status": str(exc)[:80]})
        answer = (
            f"{index} market context (deterministic fallback; no cloud LLM response succeeded): "
            f"LTP={market.get('ltp') if market.get('ltp') is not None else 'unavailable'}; "
            f"quote age={market.get('age_seconds') if market.get('age_seconds') is not None else 'unknown'} seconds; "
            f"signal={signal.get('decision', 'WAIT')}; validation={validation.get('verdict', 'NOT_AVAILABLE')}. "
            f"Reason: {'; '.join(str(item) for item in reasons[:5]) or 'No verified signal explanation returned'}. "
            "Missing/stale evidence blocks action. This API is signal-only and never places broker orders."
        )
        return {
            "answer": answer, "provider": "deterministic_fallback",
            "model": "five-layer-quant-context", "llm_used": False,
            "index": index, "question": question, "market": market, "signal": signal,
            "validation": validation, "search_attempted": bool(os.getenv("EXA_API_KEY", "").strip() or os.getenv("TAVILY_API_KEY", "").strip()),
            "search_evidence": list(news.get("articles") or [])[:8],
            "provider_failures": failures, "status": "provider_error_fallback" if failures else "fallback_response",
            "signal_only": True, "order_placement_enabled": False,
        }
    except HTTPException as exc:
        raise HTTPException(status_code=503, detail={"message": "Current market context is unavailable.", "reason": str(exc.detail)[:180]}) from exc


@app.get("/v1/live/orders")
def live_orders(_: str = Depends(_device)) -> dict[str, Any]:
    adapter = _current_adapter()
    if not adapter or adapter.status().get("authenticated") is not True:
        return {
            "status": "not_connected", "orders": [], "order_placement_enabled": False,
            "message": "Connect Angel One to read the broker order book. No order-placement API is exposed.",
        }
    try:
        snapshot = adapter.account_snapshot()
        return {
            "status": snapshot.get("status", "unavailable"),
            "orders": snapshot.get("orders", []), "errors": snapshot.get("errors", []),
            "read_only": True, "order_placement_enabled": False,
            "message": "Read-only Angel One order-book snapshot; this endpoint cannot submit or modify orders.",
        }
    except Exception:
        return {
            "status": "unavailable", "orders": [], "order_placement_enabled": False,
            "message": "Angel One order-book read failed. Check session and broker API access.",
        }


@app.get("/v1/portfolio")
def portfolio(_: str = Depends(_device)) -> dict[str, Any]:
    adapter = _current_adapter()
    if not adapter or adapter.status().get("authenticated") is not True:
        return {
            "status": "not_connected", "positions": [], "holdings": [], "orders": [],
            "source": "angelone_smartapi", "read_only": True,
            "message": "Connect Angel One to load live holdings and positions. No sample balance or P&L is fabricated.",
        }
    try:
        snapshot = adapter.account_snapshot()
        return {
            **snapshot,
            "message": "Authenticated read-only account snapshot. Missing broker endpoints remain empty and are listed in errors.",
            "order_placement_enabled": False,
        }
    except Exception:
        return {
            "status": "unavailable", "positions": [], "holdings": [], "orders": [],
            "source": "angelone_smartapi", "read_only": True,
            "message": "Angel One account snapshot failed. Check session and broker API access.",
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
    supported_instruments = set(INDEXES) | set(COMMODITY_NAMES)
    if index not in supported_instruments:
        raise HTTPException(status_code=422, detail=f"Unsupported instrument. Choose from {', '.join(sorted(supported_instruments))}.")
    if side not in {"CALL", "PUT", "CALL BUY", "PUT BUY", "LONG", "SHORT"}:
        raise HTTPException(status_code=422, detail="Unsupported paper-trade side.")
    entry_price = _number(body.get("entry_price"))
    stop_loss = _number(body.get("stop_loss"))
    target = _number(body.get("target"))
    quantity = _number(body.get("quantity"))
    lot_size = _number(body.get("lot_size"))
    for field, value in (("entry_price", entry_price), ("stop_loss", stop_loss), ("target", target), ("quantity", quantity), ("lot_size", lot_size)):
        if body.get(field) is not None and (value is None or value <= 0):
            raise HTTPException(status_code=422, detail=f"{field} must be a finite positive number.")
    slippage_inr = _number(body.get("slippage_inr"))
    brokerage_inr = _number(body.get("brokerage_inr"))
    other_costs_inr = _number(body.get("other_costs_inr"))
    slippage_inr = 0.0 if slippage_inr is None else slippage_inr
    brokerage_inr = 0.0 if brokerage_inr is None else brokerage_inr
    other_costs_inr = 0.0 if other_costs_inr is None else other_costs_inr
    if min(slippage_inr, brokerage_inr, other_costs_inr) < 0:
        raise HTTPException(status_code=422, detail="Rupee-denominated costs cannot be negative.")
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
        "index": index, "instrument": index,
        "instrument_type": "MCX" if index in COMMODITY_NAMES else "INDEX",
        "side": side, "regime": str(body.get("regime") or "UNVERIFIED")[:64],
        "option_type": str(body.get("option_type") or "").upper()[:8] or None,
        "strike": _number(body.get("strike")), "expiry": str(body.get("expiry") or "")[:32] or None,
        "entry_price": entry_price, "stop_loss": stop_loss, "target": target,
        "quantity": quantity, "lot_size": lot_size,
        "status": "OPEN", "slippage_r": slippage_r, "transaction_cost_r": transaction_cost_r,
        "slippage_inr": slippage_inr, "brokerage_inr": brokerage_inr, "other_costs_inr": other_costs_inr,
        "gross_r": None, "net_r": None, "gross_pnl_inr": None, "net_pnl_inr": None,
        "exit_price": None, "exit_reason": None,
        "notes": str(body.get("notes") or "")[:1000],
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
    exit_price = _number(body.get("exit_price"))
    exit_reason = str(body.get("exit_reason") or "MANUAL").strip().upper().replace(" ", "_")[:40]
    if exit_reason not in {"TARGET", "TARGET_HIT", "TAKE_PROFIT", "STOP_LOSS", "SL", "STOP_FIRST_BOTH_TOUCHED", "MANUAL", "MAX_HOLD", "SIGNAL_EXIT", "END_OF_DATA"}:
        raise HTTPException(status_code=422, detail="Unsupported exit_reason.")
    rows = _load_paper_trades()
    trade = next((item for item in rows if str(item.get("trade_id")) == trade_id), None)
    if trade is None:
        raise HTTPException(status_code=404, detail="Paper trade not found.")
    if trade.get("status") == "CLOSED":
        raise HTTPException(status_code=409, detail="Paper trade is already closed.")
    entry_price = _number(trade.get("entry_price"))
    stop_loss = _number(trade.get("stop_loss"))
    quantity = _number(trade.get("quantity"))
    lot_size = _number(trade.get("lot_size")) or 1.0
    is_short = str(trade.get("side") or "").upper() == "SHORT"
    if gross_r is None and exit_price is not None and entry_price is not None and stop_loss is not None and abs(entry_price - stop_loss) > 0:
        gross_r = ((entry_price - exit_price) if is_short else (exit_price - entry_price)) / abs(entry_price - stop_loss)
    if gross_r is None:
        raise HTTPException(status_code=422, detail="Provide gross_r, or provide exit_price for a trade with entry_price and stop_loss.")
    net_r = gross_r - float(trade.get("slippage_r") or 0) - float(trade.get("transaction_cost_r") or 0)
    gross_pnl_inr = None
    net_pnl_inr = None
    if exit_price is not None and entry_price is not None and quantity is not None and quantity > 0:
        gross_pnl_inr = ((entry_price - exit_price) if is_short else (exit_price - entry_price)) * quantity * lot_size
        total_cost_inr = sum(float(trade.get(key) or 0) for key in ("slippage_inr", "brokerage_inr", "other_costs_inr"))
        # Optional close-time costs can override/add to the costs saved when the paper trade opened.
        for key in ("slippage_inr", "brokerage_inr", "other_costs_inr"):
            extra = _number(body.get(key))
            if extra is not None:
                if extra < 0:
                    raise HTTPException(status_code=422, detail=f"{key} cannot be negative.")
                total_cost_inr += extra
        net_pnl_inr = gross_pnl_inr - total_cost_inr
    trade.update({
        "status": "CLOSED", "gross_r": round(gross_r, 6), "net_r": round(net_r, 6),
        "exit_price": exit_price, "exit_reason": exit_reason,
        "gross_pnl_inr": round(gross_pnl_inr, 2) if gross_pnl_inr is not None else None,
        "net_pnl_inr": round(net_pnl_inr, 2) if net_pnl_inr is not None else None,
        "closed_at": _utc_now().isoformat(),
        "notes": (str(trade.get("notes") or "") + (" | " if trade.get("notes") and body.get("notes") else "") + str(body.get("notes") or ""))[:1500],
    })
    persisted = _save_paper_trades(rows)
    return {
        "status": "ok", "trade": trade, "persistence": "persistent" if persisted else "memory_only",
        "message": "Paper result recorded after deducting the configured R-costs; no broker order was submitted.",
    }


def _paper_performance_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [item for item in trades if item.get("status") == "CLOSED" and _number(item.get("net_r")) is not None]
    net_values = [float(item["net_r"]) for item in closed]
    gross_values = [_number(item.get("gross_r")) for item in closed]
    wins = [value for value in net_values if value > 0]
    losses = [value for value in net_values if value < 0]
    flats = [value for value in net_values if value == 0]
    reasons = [str(item.get("exit_reason") or "").upper() for item in closed]
    target_reasons = {"TARGET", "TARGET_HIT", "TAKE_PROFIT"}
    stop_reasons = {"STOP_LOSS", "SL", "STOP_FIRST_BOTH_TOUCHED"}
    pnl_values = [_number(item.get("net_pnl_inr")) for item in closed]
    has_complete_inr_pnl = bool(closed) and all(value is not None for value in pnl_values)

    def metrics_for(items: list[dict[str, Any]]) -> dict[str, Any]:
        values = [float(item["net_r"]) for item in items if _number(item.get("net_r")) is not None]
        item_wins = [value for value in values if value > 0]
        item_losses = [value for value in values if value < 0]
        item_flats = [value for value in values if value == 0]
        item_reasons = [str(item.get("exit_reason") or "").upper() for item in items]
        gross = [_number(item.get("gross_r")) for item in items]
        rupee_values = [_number(item.get("net_pnl_inr")) for item in items]
        complete_rupees = bool(items) and all(value is not None for value in rupee_values)
        count = len(values)
        return {
            "trade_count": count,
            "win_count": len(item_wins),
            "loss_count": len(item_losses),
            "breakeven_count": len(item_flats),
            "win_rate": len(item_wins) / count if count else None,
            "loss_rate": len(item_losses) / count if count else None,
            "target_hits": sum(1 for reason in item_reasons if reason in target_reasons),
            "stop_loss_hits": sum(1 for reason in item_reasons if reason in stop_reasons),
            "target_hit_rate": sum(1 for reason in item_reasons if reason in target_reasons) / count if count else None,
            "stop_loss_rate": sum(1 for reason in item_reasons if reason in stop_reasons) / count if count else None,
            "gross_total_r": round(sum(value for value in gross if value is not None), 6),
            "net_total_r": round(sum(values), 6),
            "net_pnl_inr": round(sum(value for value in rupee_values if value is not None), 2) if complete_rupees else None,
            "profit_factor": round(sum(item_wins) / abs(sum(item_losses)), 6) if item_losses else (None if not item_wins else None),
            "pnl_status": "RECORDED" if complete_rupees else "NOT_AVAILABLE_FOR_ALL_TRADES",
        }

    by_instrument: dict[str, list[dict[str, Any]]] = {}
    for item in closed:
        instrument = str(item.get("instrument") or item.get("index") or "UNKNOWN").upper()
        by_instrument.setdefault(instrument, []).append(item)
    overall = metrics_for(closed)
    overall["open_trade_count"] = sum(1 for item in trades if item.get("status") == "OPEN")
    overall["total_slippage_r"] = round(sum(float(item.get("slippage_r") or 0) for item in closed), 6)
    overall["total_transaction_cost_r"] = round(sum(float(item.get("transaction_cost_r") or 0) for item in closed), 6)
    overall["total_costs_inr"] = round(sum(float(item.get("slippage_inr") or 0) + float(item.get("brokerage_inr") or 0) + float(item.get("other_costs_inr") or 0) for item in closed), 2)
    return {
        "trade_count": len(closed),
        "metrics": overall,
        "by_instrument": {key: metrics_for(value) for key, value in sorted(by_instrument.items())},
        "trades": closed,
        "mode": "PAPER_ONLY",
        "accuracy_status": "UNVERIFIED_NO_CLOSED_TRADES" if not closed else "RECORDED_PAPER_OUTCOMES",
        "message": "Only closed, explicitly recorded paper outcomes are counted. INR net P&L is shown only when every closed trade has entry/exit price, quantity and cost data; this is not live broker P&L.",
    }


@app.get("/v1/paper/report")
def paper_report(_: str = Depends(_device)) -> dict[str, Any]:
    rows = _load_paper_trades()
    report = _paper_performance_summary(rows)
    report.update({
        "status": "ok",
        "persistence": "persistent" if _paper_trade_path().is_file() else "memory_or_empty",
        "signal_only": True,
        "order_placement_enabled": False,
    })
    return report


@app.post("/v1/strategies/evaluate")
def evaluate_strategies(body: dict[str, Any], _: str = Depends(_device)) -> dict[str, Any]:
    """Evaluate supplied completed candles with the local research strategy suite."""
    candles = body.get("candles")
    if not isinstance(candles, list) or not candles:
        raise HTTPException(status_code=422, detail="candles must be a non-empty list.")
    if len(candles) > 5000:
        raise HTTPException(status_code=422, detail="At most 5000 candles may be evaluated per request.")
    raw_consensus = body.get("min_consensus", 3)
    if isinstance(raw_consensus, bool) or not isinstance(raw_consensus, int) or not 1 <= raw_consensus <= 8:
        raise HTTPException(status_code=422, detail="min_consensus must be an integer from 1 to 8.")
    reward_risk = _number(body.get("risk_reward", 2.0))
    if reward_risk is None or reward_risk <= 0 or reward_risk > 10:
        raise HTTPException(status_code=422, detail="risk_reward must be finite and between 0 and 10.")
    # Trace the exact submitted input so the UI can distinguish an evaluated
    # strategy result from a static catalogue entry. This endpoint does not call
    # an AI provider or propagate results to another engine.
    input_hash = hashlib.sha256(
        json.dumps(candles, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    execution_id = f"strategy-{uuid.uuid4().hex}"
    evaluated_at = _utc_now().isoformat()
    result = evaluate_strategy_suite(
        candles,
        oi_change=body.get("oi_change"),
        min_consensus=raw_consensus,
        risk_reward=reward_risk,
    )
    trace = {
        "execution_id": execution_id,
        "strategy_version": "strategy-suite-v1",
        "evaluated_at": evaluated_at,
        "input_candle_count": len(candles),
        "input_sha256": input_hash,
        "source": "submitted_completed_candles",
        "ai_consumed": False,
        "ai_consumption_status": "NOT_CONNECTED_TO_THIS_ENDPOINT",
        "research_engine_received": False,
        "trading_setup_received": False,
        "downstream_status": "NOT_CONNECTED",
    }
    # Per-strategy trace records the actual returned rule output. A catalogue
    # entry alone is never treated as an execution, and scores are not fabricated.
    strategy_outputs = result.get("strategies") if isinstance(result.get("strategies"), dict) else {}
    strategy_trace = []
    for strategy_name, strategy_signal in strategy_outputs.items():
        signal_text = str(strategy_signal or "WAIT").upper()
        strategy_trace.append({
            "strategy_id": f"{execution_id}:{strategy_name}",
            "strategy_name": strategy_name,
            "strategy_version": "strategy-suite-v1",
            "execution_id": execution_id,
            "signal": signal_text,
            "score": None,
            "score_status": "NOT_COMPUTED_BY_RULE",
            "input_candle_count": len(candles),
            "input_sha256": input_hash,
            "source": "submitted_completed_candles",
            "status": "evaluated",
            "rejection_reason": (
                None if signal_text in ("LONG", "SHORT")
                else "No directional LONG/SHORT event was returned for the final evaluated candle; WAIT is not a trade."
            ),
            "ai_consumed": False,
            "research_engine_received": False,
            "trading_setup_received": False,
            "order_placement_enabled": False,
        })
    return {
        **result,
        "source": "submitted_completed_candles",
        "execution_id": execution_id,
        "trace": trace,
        "strategy_trace": strategy_trace,
        "order_placement_enabled": False,
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