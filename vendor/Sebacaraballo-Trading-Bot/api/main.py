"""
api/main.py
-----------
FastAPI backend for the Phase 5 dashboard.

Serves read-only JSON over the Phase 1/2 SQLite database.  Reuses the
existing storage.database.Database class for all DB access — no schema
or connection logic is duplicated here.

Run from the project root:
    uvicorn api.main:app --reload

Endpoints:
    GET /api/health
    GET /api/stats
    GET /api/signals            ?ticker=&limit=
    GET /api/signals/{id}
    GET /api/filings            ?ticker=&limit=
    GET /api/filings/{id}/text
    GET /api/backtest/latest
    GET /api/backtest/runs

Schema notes (important — differs from the dashboard spec):
  * The DB file is ``earnings_intel.db`` in the project root.
  * Signal sentiment / bull_case / bear_case / risk_flags / guidance_quality /
    management_tone live inside the ``signals.key_metrics`` JSON blob, NOT as
    top-level columns.  This module parses that blob and flattens the fields
    into the API response.
  * The real ``key_metrics`` keys are eps_beat / revenue_beat / guidance_quality
    (not revenue_yoy_growth / gross_margin).  The full parsed blob is returned
    under ``key_metrics`` so the frontend can render whatever is present.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from storage.database import Database
from backtest.store import get_latest_backtest, list_backtest_runs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

# DB_PATH is set in production (Railway); defaults to the project-root DB locally.
db_path = os.getenv("DB_PATH", "earnings_intel.db")
db = Database(db_path)

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Earnings Intelligence API",
    version="0.5.0",
    description="Read-only API serving SEC 8-K signals for the Phase 5 dashboard.",
)

# Comma-separated list of allowed origins. In production set ALLOWED_ORIGINS to
# the deployed Vercel URL(s); defaults to the local Vite dev server.
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# direction (DB enum) → sentiment (UI enum), used as a fallback when the
# key_metrics blob is missing a "sentiment" key.
_DIRECTION_TO_SENTIMENT = {
    "LONG": "bullish",
    "SHORT": "bearish",
    "NEUTRAL": "neutral",
}


def _safe_json(blob: Optional[str], default: Any) -> Any:
    """Parse a JSON string column, returning *default* on null / empty / bad JSON."""
    if not blob:
        return default
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse JSON blob: %.80s", blob)
        return default


def _assemble_signal(row: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten a raw ``signals`` row (joined with ticker/filing_date) into the
    API response shape, pulling nested fields out of the key_metrics blob.
    """
    km = _safe_json(row.get("key_metrics"), {})
    if not isinstance(km, dict):
        km = {}

    sentiment = km.get("sentiment") or _DIRECTION_TO_SENTIMENT.get(
        row.get("direction", ""), "neutral"
    )

    risk_flags = km.get("risk_flags") or []
    if not isinstance(risk_flags, list):
        risk_flags = []

    return {
        "id": row["id"],
        "filing_id": row["filing_id"],
        "ticker": row.get("ticker"),
        "filing_date": row.get("signal_date"),
        "sentiment": sentiment,
        "confidence": row.get("confidence"),
        "direction": row.get("direction"),
        "guidance_quality": km.get("guidance_quality"),
        "management_tone": km.get("management_tone"),
        "risk_flags": risk_flags,
        "key_metrics": km,
        "bull_case": km.get("bull_case", ""),
        "bear_case": km.get("bear_case", ""),
        "reasoning": row.get("reasoning", ""),
        "llm_model": row.get("llm_model"),
        "created_at": row.get("created_at"),
    }


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a SELECT and return a list of plain dicts (row_factory is sqlite3.Row)."""
    rows = db._conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe — confirms the API is up and which DB it is serving."""
    return {"status": "ok", "db_path": db.db_path}


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    """
    Aggregate counts for the Overview page.

    Returns counts of companies / filings / signals / earnings_dates, plus the
    distinct list of tickers that currently have at least one signal.
    """

    def _count(table: str) -> int:
        try:
            return db._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        except Exception:
            return 0

    analyzed = _query(
        """
        SELECT DISTINCT c.ticker
        FROM   signals   s
        JOIN   companies c ON c.id = s.company_id
        ORDER BY c.ticker
        """
    )

    return {
        "companies": _count("companies"),
        "filings": _count("filings"),
        "signals": _count("signals"),
        "earnings_dates": _count("earnings_dates"),
        "analyzed_tickers": [r["ticker"] for r in analyzed],
    }


@app.get("/api/signals")
def list_signals(ticker: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    """
    List signals (newest first), optionally filtered by ticker.

    Each item joins the signal with its filing's ticker and date, and flattens
    the key_metrics JSON blob into top-level fields.
    """
    limit = max(1, min(limit, 500))
    where = "WHERE c.ticker = ?" if ticker else ""
    params: tuple = (ticker.upper(), limit) if ticker else (limit,)

    rows = _query(
        f"""
        SELECT s.id, s.filing_id, s.signal_date, s.direction, s.confidence,
               s.reasoning, s.key_metrics, s.llm_model, s.created_at,
               c.ticker
        FROM   signals   s
        JOIN   companies c ON c.id = s.company_id
        {where}
        ORDER BY s.signal_date DESC, s.id DESC
        LIMIT ?
        """,
        params,
    )
    return [_assemble_signal(r) for r in rows]


@app.get("/api/signals/{signal_id}")
def get_signal(signal_id: int) -> dict[str, Any]:
    """Return a single signal in full detail, or 404 if not found."""
    rows = _query(
        """
        SELECT s.id, s.filing_id, s.signal_date, s.direction, s.confidence,
               s.reasoning, s.key_metrics, s.llm_model, s.created_at,
               c.ticker
        FROM   signals   s
        JOIN   companies c ON c.id = s.company_id
        WHERE  s.id = ?
        """,
        (signal_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return _assemble_signal(rows[0])


@app.get("/api/filings")
def list_filings(ticker: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    """
    List filings (newest first), optionally filtered by ticker.

    ``text_length`` is the character length of the cleaned filing text.
    ``has_signal`` is True when a signal row references this filing.
    """
    limit = max(1, min(limit, 500))
    where = "WHERE c.ticker = ?" if ticker else ""
    params: tuple = (ticker.upper(), limit) if ticker else (limit,)

    rows = _query(
        f"""
        SELECT f.id,
               f.filing_date,
               f.form_type,
               LENGTH(COALESCE(f.cleaned_text, '')) AS text_length,
               f.fetch_status,
               c.ticker,
               CASE WHEN s.id IS NULL THEN 0 ELSE 1 END AS has_signal
        FROM   filings   f
        JOIN   companies c ON c.id = f.company_id
        LEFT JOIN signals s ON s.filing_id = f.id
        {where}
        ORDER BY f.filing_date DESC, f.id DESC
        LIMIT ?
        """,
        params,
    )
    for r in rows:
        r["has_signal"] = bool(r["has_signal"])
    return rows


@app.get("/api/filings/{filing_id}/text")
def get_filing_text(filing_id: int) -> dict[str, Any]:
    """Return the cleaned text of a single filing for the viewer drawer."""
    rows = _query(
        """
        SELECT c.ticker,
               f.filing_date,
               COALESCE(f.cleaned_text, '') AS text
        FROM   filings   f
        JOIN   companies c ON c.id = f.company_id
        WHERE  f.id = ?
        """,
        (filing_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Filing {filing_id} not found")
    return rows[0]


# ---------------------------------------------------------------------------
# Backtest endpoints (Phase 3)
# ---------------------------------------------------------------------------

@app.get("/api/backtest/latest")
def backtest_latest() -> dict[str, Any]:
    """
    Return the most recent backtest run in full (metrics + trades + equity curve),
    or 404 if no backtest has been run yet.
    """
    result = get_latest_backtest(db)
    if result is None:
        raise HTTPException(status_code=404, detail="No backtest run yet")
    return result


@app.get("/api/backtest/runs")
def backtest_runs() -> list[dict[str, Any]]:
    """Return lightweight summaries of all backtest runs (newest first)."""
    return list_backtest_runs(db)
