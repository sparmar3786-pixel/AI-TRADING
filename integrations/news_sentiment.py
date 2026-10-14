"""Bounded Exa/Tavily market-news context; never overrides deterministic risk gates."""
from __future__ import annotations

import json
import os
import urllib.error
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

_CACHE_TTL_SECONDS = 600
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()

_QUERIES = {
    "NIFTY": "India Nifty 50 stock market today NSE market news",
    "BANKNIFTY": "India Bank Nifty banking stocks RBI market news today",
    "FINNIFTY": "India financial services stocks market news today",
    "MIDCPNIFTY": "India midcap stocks market news today",
    "SENSEX": "India BSE Sensex stock market news today",
    "BANKEX": "India BSE banking index market news today",
    "MCX": "India MCX commodity market news crude oil natural gas gold silver copper futures today",
}

_POSITIVE = (
    "bullish", "rally", "surge", "gain", "gains", "rise", "rises", "strong",
    "record high", "beat estimates", "inflow", "upgrade", "breakout", "rebound",
    "higher", "outperform", "buying interest", "eases",
)
_NEGATIVE = (
    "bearish", "fall", "falls", "drop", "drops", "decline", "selloff", "sell-off",
    "crash", "weak", "outflow", "downgrade", "miss estimates", "risk-off",
    "geopolitical tension", "war", "inflation concern", "slump", "lower",
    "underperform", "volatility spike",
)


def score_news_articles(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Score headlines conservatively and transparently; not a probability of profit."""
    scored: list[dict[str, Any]] = []
    for article in articles:
        title = str(article.get("title") or "").strip()
        content = str(article.get("content") or article.get("text") or "")
        text = (title + " " + content[:1800]).lower()
        if not title:
            continue
        positive = sum(text.count(term) for term in _POSITIVE)
        negative = sum(text.count(term) for term in _NEGATIVE)
        denom = positive + negative
        polarity = 0.0 if denom == 0 else (positive - negative) / denom
        scored.append({
            "title": title[:240],
            "url": str(article.get("url") or "")[:700],
            "published_at": article.get("published_at") or article.get("publishedDate"),
            "source": str(article.get("source") or "news_search"),
            "polarity_score": round(polarity, 3),
        })
    if not scored:
        return {"status": "NO_EVIDENCE", "label": "UNKNOWN", "score": None, "article_count": 0, "articles": []}
    score = sum(item["polarity_score"] for item in scored) / len(scored)
    label = "BULLISH" if score >= 0.12 else "BEARISH" if score <= -0.12 else "NEUTRAL"
    return {
        "status": "LIVE_EVIDENCE",
        "label": label,
        "score": round(score, 3),
        "article_count": len(scored),
        "articles": scored[:8],
    }


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def cached_market_news_sentiment(index: str) -> dict[str, Any]:
    """Return cached evidence immediately without performing network I/O."""
    key = index.strip().upper()
    with _lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
    if not (os.getenv("EXA_API_KEY", "").strip() or os.getenv("TAVILY_API_KEY", "").strip()):
        return {
            "status": "NOT_CONFIGURED", "label": "UNKNOWN", "score": None,
            "article_count": 0, "sources": [], "articles": [],
            "window_hours": 24,
            "message": "Configure Exa or Tavily server-side to enable headline context.",
        }
    return {
        "status": "PENDING", "label": "UNKNOWN", "score": None,
        "article_count": 0, "sources": [], "articles": [],
        "window_hours": 24, "message": "Refreshing last-24-hour headline context in the background.",
    }


def fetch_market_news_sentiment(
    index: str,
    exa_api_key: str | None = None,
    tavily_api_key: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Fetch at most a small batch of last-24h headlines, cached for ten minutes."""
    key = index.strip().upper()
    now_mono = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if not force and cached and now_mono - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

    exa_key = (exa_api_key or os.getenv("EXA_API_KEY", "")).strip()
    tavily_key = (tavily_api_key or os.getenv("TAVILY_API_KEY", "")).strip()
    if not exa_key and not tavily_key:
        return {
            "status": "NOT_CONFIGURED", "label": "UNKNOWN", "score": None,
            "article_count": 0, "sources": [], "articles": [],
            "window_hours": 24,
            "message": "Configure Exa or Tavily server-side to enable headline context.",
        }

    query = _QUERIES.get(key, f"India financial markets {key} market news today")
    start_date = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    articles: list[dict[str, Any]] = []
    sources: list[str] = []
    errors: list[str] = []
    provider_checks: dict[str, dict[str, Any]] = {}

    if exa_key:
        try:
            payload = _post_json(
                "https://api.exa.ai/search",
                {
                    "query": query,
                    "type": "auto",
                    "numResults": 8,
                    "startPublishedDate": start_date,
                    "contents": {"text": {"maxCharacters": 1200}},
                },
                {"x-api-key": exa_key},
            )
            results = payload.get("results") if isinstance(payload.get("results"), list) else []
            for item in results[:8]:
                if isinstance(item, dict):
                    articles.append({
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "published_at": item.get("publishedDate"),
                        "content": item.get("text", ""),
                        "source": "exa",
                    })
            provider_checks["exa"] = {"configured": True, "ok": True, "status": "ok", "result_count": len(results)}
            if results:
                sources.append("exa")
        except urllib.error.HTTPError as exc:
            status = "rate_limited" if exc.code == 429 else "authentication_failed" if exc.code in (401, 403) else f"http_{exc.code}"
            provider_checks["exa"] = {"configured": True, "ok": False, "status": status, "result_count": 0}
            errors.append(f"exa_{status}")
        except Exception as exc:
            provider_checks["exa"] = {"configured": True, "ok": False, "status": "connection_or_response_error", "result_count": 0}
            errors.append("exa_connection_or_response_error")

    if tavily_key:
        try:
            payload = _post_json(
                "https://api.tavily.com/search",
                {
                    "query": query,
                    "topic": "news",
                    "days": 1,
                    "max_results": 8,
                    "include_answer": False,
                    "include_raw_content": False,
                },
                {"Authorization": f"Bearer {tavily_key}"},
            )
            results = payload.get("results") if isinstance(payload.get("results"), list) else []
            for item in results[:8]:
                if isinstance(item, dict):
                    articles.append({
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "published_at": item.get("published_date"),
                        "content": item.get("content", ""),
                        "source": "tavily",
                    })
            provider_checks["tavily"] = {"configured": True, "ok": True, "status": "ok", "result_count": len(results)}
            if results:
                sources.append("tavily")
        except urllib.error.HTTPError as exc:
            status = "rate_limited" if exc.code == 429 else "authentication_failed" if exc.code in (401, 403) else f"http_{exc.code}"
            provider_checks["tavily"] = {"configured": True, "ok": False, "status": status, "result_count": 0}
            errors.append(f"tavily_{status}")
        except Exception:
            provider_checks["tavily"] = {"configured": True, "ok": False, "status": "connection_or_response_error", "result_count": 0}
            errors.append("tavily_connection_or_response_error")

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in articles:
        identity = str(item.get("url") or item.get("title") or "").strip().lower()
        if identity and identity not in seen:
            seen.add(identity)
            unique.append(item)

    result = score_news_articles(unique)
    result.update({
        "sources": sorted(set(sources)),
        "provider_checks": provider_checks,
        "window_hours": 24,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
        "use": "context_only_not_a_trade_trigger",
    })
    with _lock:
        _cache[key] = (time.monotonic(), result)
    return result
