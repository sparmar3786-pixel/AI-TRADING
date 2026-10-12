"""
storage/database.py
-------------------
SQLite persistence layer for the Earnings Intelligence System.

Schema is designed for all four phases:
  Phase 1 — companies, earnings_dates, filings        (this file)
  Phase 2 — signals  (LLM-extracted trade signals)
  Phase 3 — backtest_runs                             (future)
  Phase 4 — trades   (Alpaca paper trades)            (future)
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- ── Phase 1 ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL UNIQUE,
    cik         TEXT    NOT NULL UNIQUE,
    name        TEXT,
    exchange    TEXT,
    sector      TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS earnings_dates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id       INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    earnings_date    TIMESTAMP NOT NULL,
    eps_estimate     REAL,
    eps_actual       REAL,
    surprise_pct     REAL,
    revenue_estimate REAL,
    revenue_actual   REAL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, earnings_date)
);

CREATE TABLE IF NOT EXISTS filings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id       INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    accession_number TEXT    NOT NULL UNIQUE,
    filing_date      DATE    NOT NULL,
    form_type        TEXT    NOT NULL DEFAULT '8-K',
    period_of_report DATE,
    primary_document TEXT,
    document_url     TEXT,
    raw_html         TEXT,
    cleaned_text     TEXT,
    word_count       INTEGER,
    fetch_status     TEXT    DEFAULT 'pending'
                             CHECK(fetch_status IN ('pending', 'success', 'failed')),
    error_message    TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Phase 2: LLM trade signals ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signals (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id             INTEGER NOT NULL REFERENCES filings(id),
    company_id            INTEGER NOT NULL REFERENCES companies(id),
    signal_date           TIMESTAMP NOT NULL,
    direction             TEXT    CHECK(direction IN ('LONG', 'SHORT', 'NEUTRAL')),
    confidence            REAL    CHECK(confidence BETWEEN 0.0 AND 1.0),
    reasoning             TEXT,
    -- JSON blob: {"eps_beat": true, "revenue_surprise_pct": 2.3, "guidance": "raised"}
    key_metrics           TEXT,
    llm_model             TEXT,
    llm_prompt_tokens     INTEGER,
    llm_completion_tokens INTEGER,
    raw_llm_response      TEXT,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Phase 3: Backtesting ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS backtest_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_name        TEXT,
    start_date      DATE,
    end_date        DATE,
    tickers         TEXT,   -- JSON array, e.g. '["AAPL","MSFT"]'
    strategy_config TEXT,   -- JSON blob of hyperparameters
    total_trades    INTEGER,
    winning_trades  INTEGER,
    total_pnl       REAL,
    sharpe_ratio    REAL,
    max_drawdown    REAL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Phase 3 result fields (added via _migrate_backtest_columns for old DBs).
    -- All ratio/return fields are stored as DECIMAL FRACTIONS (0.05 == 5%).
    run_date                TEXT,
    confidence_threshold    REAL,
    total_signals_evaluated INTEGER,
    trades_skipped          INTEGER,
    win_rate                REAL,
    avg_return_pct          REAL,
    total_return_pct        REAL,
    spy_return_pct          REAL,
    trades_json             TEXT,   -- JSON list of per-trade dicts
    equity_curve_json       TEXT    -- JSON list of {date, value} points
);

-- ── Phase 4: Alpaca paper trades ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trades (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id           INTEGER REFERENCES signals(id),
    company_id          INTEGER NOT NULL REFERENCES companies(id),
    ticker              TEXT    NOT NULL,
    direction           TEXT    CHECK(direction IN ('BUY', 'SELL')),
    quantity            REAL,
    entry_price         REAL,
    exit_price          REAL,
    entry_time          TIMESTAMP,
    exit_time           TIMESTAMP,
    pnl                 REAL,
    pnl_pct             REAL,
    hold_duration_mins  INTEGER,
    status              TEXT    DEFAULT 'PENDING'
                                CHECK(status IN ('PENDING','OPEN','CLOSED','CANCELLED','REJECTED')),
    alpaca_order_id     TEXT,
    alpaca_account_id   TEXT,
    strategy_version    TEXT,
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Indexes ───────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_earnings_company  ON earnings_dates(company_id, earnings_date DESC);
CREATE INDEX IF NOT EXISTS idx_filings_company   ON filings(company_id, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_filings_status    ON filings(fetch_status);
CREATE INDEX IF NOT EXISTS idx_signals_company   ON signals(company_id, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_filing    ON signals(filing_id);
CREATE INDEX IF NOT EXISTS idx_trades_status     ON trades(status, company_id);
CREATE INDEX IF NOT EXISTS idx_trades_signal     ON trades(signal_id);
"""


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

class Database:
    """
    SQLite wrapper providing typed upsert/query methods for all system phases.

    Uses WAL journal mode for better concurrent read performance and enables
    foreign key enforcement on every connection.

    Args:
        db_path: Path to the SQLite file.  Defaults to ``earnings_intel.db``
                 in the current working directory.
    """

    def __init__(self, db_path: str = "earnings_intel.db") -> None:
        self.db_path = str(Path(db_path).resolve())
        self._conn: sqlite3.Connection = sqlite3.connect(
            self.db_path, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        logger.debug("Database initialised at %s", self.db_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create all tables and indexes if they do not already exist."""
        self._conn.executescript(_SCHEMA_SQL)
        self._migrate_backtest_columns()
        self._migrate_filings_columns()
        self._conn.commit()

    def _migrate_filings_columns(self) -> None:
        """
        Add ``filings.skip_reason`` on databases created before the analysis
        prefilter existed. NULL = eligible for Phase 2; a value (e.g.
        'no_earnings_exhibit') permanently excludes the filing from LLM
        scoring so daily pipeline runs stop re-checking it.
        """
        existing = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(filings)")
        }
        if "skip_reason" not in existing:
            self._conn.execute("ALTER TABLE filings ADD COLUMN skip_reason TEXT")
            logger.debug("Migrated filings: added column skip_reason")

    def _migrate_backtest_columns(self) -> None:
        """
        Add the Phase 3 result columns to ``backtest_runs`` on databases created
        before Phase 3.  ``CREATE TABLE IF NOT EXISTS`` never alters an existing
        table, so we ALTER in any missing columns idempotently.
        """
        existing = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(backtest_runs)")
        }
        new_columns = {
            "run_date": "TEXT",
            "confidence_threshold": "REAL",
            "total_signals_evaluated": "INTEGER",
            "trades_skipped": "INTEGER",
            "win_rate": "REAL",
            "avg_return_pct": "REAL",
            "total_return_pct": "REAL",
            "spy_return_pct": "REAL",
            "trades_json": "TEXT",
            "equity_curve_json": "TEXT",
        }
        for name, col_type in new_columns.items():
            if name not in existing:
                self._conn.execute(
                    f"ALTER TABLE backtest_runs ADD COLUMN {name} {col_type}"
                )
                logger.debug("Migrated backtest_runs: added column %s", name)

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Yield a cursor that auto-commits on clean exit and rolls back on error."""
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    @staticmethod
    def _nullable_float(value: Any) -> Optional[float]:
        """Convert a value to float, returning None for NaN / None / empty string."""
        import math
        if value is None:
            return None
        try:
            f = float(value)
            return None if math.isnan(f) else f
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # companies
    # ------------------------------------------------------------------

    def upsert_company(
        self,
        ticker: str,
        cik: str,
        name: Optional[str] = None,
        exchange: Optional[str] = None,
        sector: Optional[str] = None,
    ) -> int:
        """
        Insert a new company or update its metadata if the ticker already exists.

        Args:
            ticker:   Stock ticker symbol (upper-case).
            cik:      10-digit zero-padded SEC CIK string.
            name:     Human-readable company name.
            exchange: Primary exchange (e.g. "NASDAQ").
            sector:   GICS sector string.

        Returns:
            The ``companies.id`` primary key for the upserted row.
        """
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (ticker, cik, name, exchange, sector)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    cik      = excluded.cik,
                    name     = COALESCE(excluded.name,     companies.name),
                    exchange = COALESCE(excluded.exchange, companies.exchange),
                    sector   = COALESCE(excluded.sector,   companies.sector),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (ticker, cik, name, exchange, sector),
            )
        row = self._conn.execute(
            "SELECT id FROM companies WHERE ticker = ?", (ticker,)
        ).fetchone()
        return row["id"]

    def get_company(self, ticker: str) -> Optional[dict[str, Any]]:
        """
        Retrieve a company record by ticker.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Dictionary of column values, or ``None`` if not found.
        """
        row = self._conn.execute(
            "SELECT * FROM companies WHERE ticker = ?", (ticker.upper(),)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # earnings_dates
    # ------------------------------------------------------------------

    def upsert_earnings_date(
        self,
        company_id: int,
        earnings_date: datetime,
        eps_estimate: Optional[float] = None,
        eps_actual: Optional[float] = None,
        surprise_pct: Optional[float] = None,
        revenue_estimate: Optional[float] = None,
        revenue_actual: Optional[float] = None,
    ) -> None:
        """
        Insert or update an earnings date record for a company.

        The UNIQUE constraint on ``(company_id, earnings_date)`` ensures
        re-running the pipeline is idempotent.

        Args:
            company_id:       FK to ``companies.id``.
            earnings_date:    Date/time of the earnings release.
            eps_estimate:     Analyst consensus EPS estimate.
            eps_actual:       Reported EPS.
            surprise_pct:     (actual - estimate) / |estimate| × 100.
            revenue_estimate: Analyst consensus revenue estimate (USD).
            revenue_actual:   Reported revenue (USD).
        """
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO earnings_dates
                    (company_id, earnings_date, eps_estimate, eps_actual,
                     surprise_pct, revenue_estimate, revenue_actual)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id, earnings_date) DO UPDATE SET
                    eps_estimate     = COALESCE(excluded.eps_estimate,     earnings_dates.eps_estimate),
                    eps_actual       = COALESCE(excluded.eps_actual,       earnings_dates.eps_actual),
                    surprise_pct     = COALESCE(excluded.surprise_pct,     earnings_dates.surprise_pct),
                    revenue_estimate = COALESCE(excluded.revenue_estimate, earnings_dates.revenue_estimate),
                    revenue_actual   = COALESCE(excluded.revenue_actual,   earnings_dates.revenue_actual)
                """,
                (
                    company_id,
                    earnings_date.isoformat(),
                    self._nullable_float(eps_estimate),
                    self._nullable_float(eps_actual),
                    self._nullable_float(surprise_pct),
                    self._nullable_float(revenue_estimate),
                    self._nullable_float(revenue_actual),
                ),
            )

    def get_earnings_dates(self, company_id: int) -> list[dict[str, Any]]:
        """
        Return all earnings date records for a company, newest first.

        Args:
            company_id: FK to ``companies.id``.

        Returns:
            List of row dictionaries sorted descending by ``earnings_date``.
        """
        rows = self._conn.execute(
            "SELECT * FROM earnings_dates WHERE company_id = ? ORDER BY earnings_date DESC",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # filings
    # ------------------------------------------------------------------

    def upsert_filing(
        self,
        company_id: int,
        accession_number: str,
        filing_date: str,
        form_type: str = "8-K",
        period_of_report: Optional[str] = None,
        primary_document: Optional[str] = None,
        document_url: Optional[str] = None,
        raw_html: Optional[str] = None,
        cleaned_text: Optional[str] = None,
        word_count: Optional[int] = None,
        fetch_status: str = "pending",
        error_message: Optional[str] = None,
    ) -> int:
        """
        Insert or update a filing record.

        On conflict (same ``accession_number``), only mutable columns
        (text content, status, error) are updated; metadata columns are
        left as-is so a failed retry doesn't overwrite a good record.

        Args:
            company_id:       FK to ``companies.id``.
            accession_number: SEC accession number (with dashes).
            filing_date:      ISO-format date string, e.g. ``"2024-11-01"``.
            form_type:        SEC form type string, e.g. ``"8-K"``.
            period_of_report: Reporting period date string.
            primary_document: Filename of primary document in the filing.
            document_url:     Full URL to the primary document.
            raw_html:         Raw HTML content of the filing.
            cleaned_text:     Plain-text version of the filing.
            word_count:       Number of words in ``cleaned_text``.
            fetch_status:     One of ``'pending'``, ``'success'``, ``'failed'``.
            error_message:    Error description if ``fetch_status == 'failed'``.

        Returns:
            The ``filings.id`` primary key for the upserted row.
        """
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO filings
                    (company_id, accession_number, filing_date, form_type,
                     period_of_report, primary_document, document_url,
                     raw_html, cleaned_text, word_count, fetch_status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(accession_number) DO UPDATE SET
                    raw_html      = COALESCE(excluded.raw_html,      filings.raw_html),
                    cleaned_text  = COALESCE(excluded.cleaned_text,  filings.cleaned_text),
                    word_count    = COALESCE(excluded.word_count,     filings.word_count),
                    fetch_status  = excluded.fetch_status,
                    error_message = excluded.error_message,
                    updated_at    = CURRENT_TIMESTAMP
                """,
                (
                    company_id,
                    accession_number,
                    filing_date,
                    form_type,
                    period_of_report,
                    primary_document,
                    document_url,
                    raw_html,
                    cleaned_text,
                    word_count,
                    fetch_status,
                    error_message,
                ),
            )
        row = self._conn.execute(
            "SELECT id FROM filings WHERE accession_number = ?", (accession_number,)
        ).fetchone()
        return row["id"]

    def get_filings(
        self, company_id: int, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Return stored filings for a company, newest first.

        Args:
            company_id: FK to ``companies.id``.
            limit:      Maximum rows to return.

        Returns:
            List of row dictionaries (``cleaned_text`` and ``raw_html`` included).
        """
        rows = self._conn.execute(
            """
            SELECT id, accession_number, filing_date, form_type, period_of_report,
                   document_url, word_count, fetch_status, error_message, created_at
            FROM filings
            WHERE company_id = ?
            ORDER BY filing_date DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_filing(self, company_id: int) -> Optional[dict[str, Any]]:
        """
        Return the most recently stored successful filing for a company,
        including its ``cleaned_text``.

        Args:
            company_id: FK to ``companies.id``.

        Returns:
            Row dictionary or ``None`` if no successful filing exists.
        """
        row = self._conn.execute(
            """
            SELECT * FROM filings
            WHERE company_id = ? AND fetch_status = 'success'
            ORDER BY filing_date DESC
            LIMIT 1
            """,
            (company_id,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # signals  (Phase 2)
    # ------------------------------------------------------------------

    def set_filing_skip_reason(self, filing_id: int, reason: Optional[str]) -> None:
        """
        Mark a filing as permanently excluded from Phase 2 analysis (or clear
        the mark with ``None``). Used by the pipeline prefilter for 8-Ks that
        carry no earnings exhibit, so daily runs stop re-fetching their index.

        Args:
            filing_id: FK to ``filings.id``.
            reason:    Short machine-readable reason (e.g. 'no_earnings_exhibit'),
                       or ``None`` to make the filing eligible again.
        """
        with self._cursor() as cur:
            cur.execute(
                "UPDATE filings SET skip_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (reason, filing_id),
            )

    def save_signal(
        self,
        filing_id: int,
        company_id: int,
        signal_date: str,
        signal,  # analysis.llm_client.EarningsSignal — avoid circular import
    ) -> int:
        """
        Persist an LLM-extracted signal to the ``signals`` table.

        Maps the :class:`~analysis.llm_client.EarningsSignal` dataclass to the
        DB schema, storing extended fields (guidance_quality, management_tone,
        risk_flags, bull_case, bear_case) in the ``key_metrics`` JSON blob.

        Args:
            filing_id:   FK to ``filings.id``.
            company_id:  FK to ``companies.id``.
            signal_date: ISO date string for the filing/signal date.
            signal:      Populated ``EarningsSignal`` dataclass.

        Returns:
            The ``signals.id`` primary key of the inserted row.

        Raises:
            sqlite3.IntegrityError: If a signal for this ``filing_id`` already
                exists (each filing gets at most one signal).
        """
        import json

        key_metrics = json.dumps(
            {
                "guidance_quality": signal.guidance_quality,
                "eps_beat":         signal.eps_beat,
                "revenue_beat":     signal.revenue_beat,
                "management_tone":  signal.management_tone,
                "risk_flags":       signal.risk_flags,
                "bull_case":        signal.bull_case,
                "bear_case":        signal.bear_case,
                "sentiment":        signal.sentiment,
            },
            ensure_ascii=False,
        )

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO signals
                    (filing_id, company_id, signal_date, direction, confidence,
                     reasoning, key_metrics, llm_model,
                     llm_prompt_tokens, llm_completion_tokens, raw_llm_response)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filing_id,
                    company_id,
                    signal_date,
                    signal.direction,
                    signal.confidence,
                    signal.reasoning,
                    key_metrics,
                    signal.model,
                    signal.prompt_tokens,
                    signal.completion_tokens,
                    signal.raw_response,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_signals(
        self,
        company_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Return stored signals for a company, newest first.

        Args:
            company_id: FK to ``companies.id``.
            limit:      Maximum rows to return.

        Returns:
            List of row dictionaries (``raw_llm_response`` excluded to keep
            output concise; query directly for the full blob).
        """
        rows = self._conn.execute(
            """
            SELECT id, filing_id, company_id, signal_date, direction,
                   confidence, reasoning, key_metrics, llm_model,
                   llm_prompt_tokens, llm_completion_tokens, created_at
            FROM   signals
            WHERE  company_id = ?
            ORDER BY signal_date DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __repr__(self) -> str:
        return f"Database(path={self.db_path!r})"
