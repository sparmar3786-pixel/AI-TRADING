"""
analysis/pipeline.py
--------------------
Orchestrates Phase 2: LLM signal extraction from SEC 8-K filings.

Full flow for each unanalyzed filing:
  1. Query DB for filings with fetch_status='success', no signals row, and no
     skip_reason mark
  2. Locate Exhibit 99.1 in the SEC filing index; filings without one are
     marked skip_reason='no_earnings_exhibit' and never re-checked
  3. Download the exhibit and run it through the LLM → structured EarningsSignal
     (subject to the optional per-run LLM call budget, ``max_llm``)
  4. Persist the signal to the signals table

Usage:
    from analysis.pipeline import SignalPipeline
    pipeline = SignalPipeline(db)
    run = pipeline.run("AAPL")
    for result in run.results:
        print(result.signal.sentiment, result.signal.confidence)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from data.sec_client import SECClient
from storage.database import Database
from analysis.exhibit_fetcher import ExhibitFetcher
from analysis.llm_client import EarningsSignal, LLMClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SignalResult:
    """Outcome of processing a single filing through the pipeline."""

    filing_id: int
    accession_number: str
    filing_date: str
    ticker: str
    signal: Optional[EarningsSignal] = None
    exhibit_found: bool = False
    llm_called: bool = False   # True when an API call was spent (success or not)
    success: bool = False
    error: Optional[str] = None


@dataclass
class PipelineRun:
    """Summary of a full pipeline run (one ticker, or all when ticker is None)."""

    ticker: Optional[str]
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0          # No Exhibit 99.1 found (marked, never re-checked)
    deferred: int = 0         # Left pending: LLM budget exhausted or transient error
    llm_calls: int = 0
    results: list[SignalResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class SignalPipeline:
    """
    End-to-end signal extraction pipeline.

    Args:
        db:         Initialized :class:`~storage.database.Database` instance.
        llm_client: Optional pre-initialized :class:`~analysis.llm_client.LLMClient`.
                    Creates one from env vars if not provided.
        sec_client: Optional pre-initialized :class:`~data.sec_client.SECClient`.
                    Creates a new one if not provided.
    """

    def __init__(
        self,
        db: Database,
        llm_client: Optional[LLMClient] = None,
        sec_client: Optional[SECClient] = None,
    ) -> None:
        self._db = db
        self._sec = sec_client or SECClient()
        self._exhibit_fetcher = ExhibitFetcher(self._sec)
        self._llm = llm_client or LLMClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pending_filings(self, ticker: Optional[str] = None) -> list[dict]:
        """
        Return successfully-fetched filings that have no signal row yet and
        no permanent skip mark (see ``filings.skip_reason``).

        Args:
            ticker: Stock ticker symbol (case-insensitive), or ``None`` to
                    return pending filings across every company (newest first).

        Returns:
            List of dicts with keys:
              ``filing_id``, ``accession_number``, ``filing_date``,
              ``period_of_report``, ``ticker``, ``cik``
        """
        sql = """
            SELECT
                f.id               AS filing_id,
                f.accession_number,
                f.filing_date,
                f.period_of_report,
                c.ticker,
                c.cik
            FROM   filings   f
            JOIN   companies c ON c.id = f.company_id
            LEFT JOIN signals s ON s.filing_id = f.id
            WHERE  f.fetch_status = 'success'
              AND  f.skip_reason IS NULL
              AND  s.id IS NULL
        """
        params: tuple = ()
        if ticker is not None:
            sql += "  AND  c.ticker = ?\n"
            params = (ticker.upper(),)
        sql += "ORDER BY f.filing_date DESC, f.accession_number"

        rows = self._db._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def process_filing(self, filing: dict) -> SignalResult:
        """
        Run the full pipeline for a single filing dict.

        Steps:
          1. Fetch Exhibit 99.1 via :class:`~analysis.exhibit_fetcher.ExhibitFetcher`
          2. Call LLM via :class:`~analysis.llm_client.LLMClient`
          3. Persist result via :meth:`~storage.database.Database.save_signal`

        Args:
            filing: Row dict as returned by :meth:`get_pending_filings`.

        Returns:
            Populated :class:`SignalResult` (``success=True`` on full success).
        """
        result = SignalResult(
            filing_id=filing["filing_id"],
            accession_number=filing["accession_number"],
            filing_date=filing["filing_date"],
            ticker=filing["ticker"],
        )

        # ── Step 1a: Locate Exhibit 99.1 (index page only, cheap) ─────
        logger.info(
            "Locating Exhibit 99.1 for %s  accession=%s",
            filing["ticker"], filing["accession_number"],
        )
        location = self._exhibit_fetcher.locate(
            accession_number=filing["accession_number"],
            cik=filing["cik"],
        )

        if location.status == "no_exhibit":
            # Permanent property of the filing (not an earnings 8-K): mark it
            # so daily runs never re-fetch this index again.
            self._db.set_filing_skip_reason(
                result.filing_id, "no_earnings_exhibit"
            )
            result.error = "No Exhibit 99.1 in filing (marked, will not retry)"
            return result

        if location.status != "ok" or not location.url:
            # Transient index failure: leave pending so a later run retries.
            result.error = "Filing index fetch failed (will retry)"
            return result

        # ── Step 1b: Download the exhibit text ────────────────────────
        exhibit_text = self._exhibit_fetcher.download(location.url)
        if not exhibit_text:
            # Download failure is transient too: leave pending.
            result.error = "Exhibit download failed (will retry)"
            return result

        result.exhibit_found = True

        # ── Step 2: LLM analysis ──────────────────────────────────────
        result.llm_called = True
        try:
            signal = self._llm.analyze_exhibit(
                ticker=filing["ticker"],
                filing_date=filing["filing_date"],
                exhibit_text=exhibit_text,
            )
            result.signal = signal
        except Exception as exc:
            logger.error(
                "LLM analysis failed for %s %s: %s",
                filing["ticker"], filing["accession_number"], exc,
            )
            result.error = f"LLM error: {exc}"
            return result

        # ── Step 3: Persist to DB ─────────────────────────────────────
        try:
            company = self._db.get_company(filing["ticker"])
            if company is None:
                raise ValueError(f"Company {filing['ticker']} not found in DB")

            self._db.save_signal(
                filing_id=result.filing_id,
                company_id=company["id"],
                signal_date=filing["filing_date"],
                signal=signal,
            )
            result.success = True
            logger.info(
                "Signal saved  %s %s → %s (confidence=%.2f)",
                filing["ticker"], filing["filing_date"],
                signal.direction, signal.confidence,
            )
        except Exception as exc:
            logger.error(
                "Failed to save signal for %s %s: %s",
                filing["ticker"], filing["accession_number"], exc,
            )
            result.error = f"DB save failed: {exc}"

        return result

    def run(
        self,
        ticker: Optional[str] = None,
        max_llm: Optional[int] = None,
        on_result=None,
    ) -> PipelineRun:
        """
        Run the signal extraction pipeline over pending filings.

        Args:
            ticker:    Stock ticker symbol, or ``None`` to process pending
                       filings for every company (newest first).
            max_llm:   Maximum number of LLM API calls to spend this run
                       (``None`` = unlimited). The exhibit prefilter keeps
                       running after the budget is exhausted, since marking
                       exhibit-less filings costs SEC index fetches only;
                       filings that would need an LLM call are left pending
                       for the next run.
            on_result: Optional callable ``(result, index, total)`` invoked
                       after each filing (used by the CLI progress display).

        Returns:
            :class:`PipelineRun` with per-filing results and aggregate stats.
        """
        start = time.monotonic()
        run = PipelineRun(ticker=ticker.upper() if ticker else None)

        pending = self.get_pending_filings(ticker)
        run.total = len(pending)
        label = ticker or "all tickers"

        if not pending:
            logger.info("No pending (unanalyzed) filings for %s", label)
            return run

        logger.info("Found %d pending filings for %s", len(pending), label)

        for i, filing in enumerate(pending, start=1):
            budget_left = max_llm is None or run.llm_calls < max_llm

            if budget_left:
                result = self.process_filing(filing)
            else:
                # Prefilter-only mode: resolve the cheap no_exhibit marks,
                # defer anything that has an exhibit to the next run.
                result = SignalResult(
                    filing_id=filing["filing_id"],
                    accession_number=filing["accession_number"],
                    filing_date=filing["filing_date"],
                    ticker=filing["ticker"],
                )
                location = self._exhibit_fetcher.locate(
                    accession_number=filing["accession_number"],
                    cik=filing["cik"],
                )
                if location.status == "no_exhibit":
                    self._db.set_filing_skip_reason(
                        filing["filing_id"], "no_earnings_exhibit"
                    )
                    result.error = "No Exhibit 99.1 in filing (marked, will not retry)"
                else:
                    result.error = "LLM budget exhausted (deferred to next run)"

            run.results.append(result)
            if result.llm_called:
                run.llm_calls += 1

            if result.success:
                run.succeeded += 1
            elif result.llm_called:
                run.failed += 1          # LLM or DB-save error after a real call
            elif result.error and "marked" in result.error:
                run.skipped += 1         # no_exhibit, permanently marked
            else:
                run.deferred += 1        # budget exhausted or transient SEC failure

            if on_result is not None:
                on_result(result, i, len(pending))

        if max_llm is not None and run.llm_calls >= max_llm and run.deferred:
            logger.info(
                "LLM budget of %d reached; %d filing(s) deferred to next run",
                max_llm, run.deferred,
            )

        run.elapsed_seconds = time.monotonic() - start
        return run
