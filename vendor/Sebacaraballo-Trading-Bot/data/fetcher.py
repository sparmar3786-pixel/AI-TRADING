"""
data/fetcher.py
---------------
Orchestrator for the Phase 1 data ingestion pipeline.

Coordinates three data sources into a single ``ingest()`` call:
  1. SEC EDGAR  – CIK resolution + 8-K filing download
  2. yfinance   – historical earnings dates + EPS data
  3. SQLite     – persistence (via Database)

Design principles:
  - Never crash the full pipeline on a single filing failure
  - Print live progress to the terminal via rich
  - Return a structured ``IngestResult`` for the CLI to render
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console

from data.market_client import EarningsRecord, MarketClient
from data.sec_client import SECClient
from storage.database import Database

logger = logging.getLogger(__name__)
_console = Console()


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FilingResult:
    """Outcome of fetching a single 8-K filing."""

    accession_number: str
    filing_date: str
    form_type: str
    word_count: Optional[int]
    success: bool
    error: Optional[str] = None


@dataclass
class IngestResult:
    """
    Aggregate result of a full ``DataFetcher.ingest()`` run.

    Consumed by ``main.py`` to render the summary panel and preview.
    """

    ticker: str
    cik: str
    company_name: str
    db_path: str
    filings: list[FilingResult] = field(default_factory=list)
    earnings_count: int = 0
    elapsed_seconds: float = 0.0
    # Populated only when ≥ 1 filing succeeded
    latest_filing_date: Optional[str] = None
    latest_filing_words: Optional[int] = None
    latest_filing_url: Optional[str] = None
    latest_filing_text: Optional[str] = None

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def filings_ok(self) -> int:
        """Number of filings successfully fetched and stored."""
        return sum(1 for f in self.filings if f.success)

    @property
    def filings_failed(self) -> int:
        """Number of filings that could not be fetched."""
        return sum(1 for f in self.filings if not f.success)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class DataFetcher:
    """
    Coordinates SEC EDGAR, yfinance, and SQLite into a single ingestion run.

    Args:
        db: Initialised ``Database`` instance to write into.
    """

    def __init__(self, db: Database) -> None:
        self.sec = SECClient()
        self.market = MarketClient()
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(self, ticker: str, filing_count: int = 5) -> IngestResult:
        """
        Run the full Phase 1 ingestion pipeline for a single ticker.

        Steps
        -----
        1. Resolve CIK from the SEC EDGAR ticker map
        2. Upsert company record (enriched with yfinance sector/exchange data)
        3. Fetch and store up to *filing_count* recent 8-K filings
        4. Fetch and store historical earnings dates from yfinance

        Individual filing failures are caught and logged; they do not abort
        the pipeline.  A ``FilingResult`` with ``success=False`` is appended
        to the result for each failed filing.

        Args:
            ticker:        Stock ticker symbol (case-insensitive).
            filing_count:  Maximum number of 8-K filings to fetch.

        Returns:
            ``IngestResult`` populated with everything that was stored.

        Raises:
            ValueError: If the ticker is not found in SEC EDGAR.
            requests.HTTPError: On unrecoverable HTTP errors during CIK lookup.
        """
        ticker = ticker.upper()
        t0 = time.monotonic()

        # ── Step 1 : Resolve CIK ─────────────────────────────────────
        _console.print(
            f"\n [bold][1/4][/bold] Resolving CIK for [bold cyan]{ticker}[/bold cyan]..."
        )
        cik = self.sec.get_cik(ticker)
        submissions = self.sec.get_submissions(cik)
        company_name: str = submissions.get("name") or ticker
        _console.print(
            f"       [green]✓[/green] CIK: [bold]{cik}[/bold]  →  {company_name}"
        )

        # ── Step 2 : Upsert company (enrich with yfinance info) ───────
        yf_info = self.market.get_company_info(ticker)
        company_id = self.db.upsert_company(
            ticker=ticker,
            cik=cik,
            name=yf_info.get("name") or company_name,
            exchange=yf_info.get("exchange"),
            sector=yf_info.get("sector"),
        )

        # ── Step 3 : Fetch 8-K filings ────────────────────────────────
        _console.print(
            f"\n [bold][2/4][/bold] Fetching {filing_count} × 8-K filings from SEC EDGAR..."
        )
        filing_metas = self.sec.get_recent_filings(cik, "8-K", filing_count)

        filing_results: list[FilingResult] = []
        latest_text: Optional[str] = None
        latest_date: Optional[str] = None
        latest_words: Optional[int] = None
        latest_url: Optional[str] = None

        if not filing_metas:
            _console.print(
                "       [yellow]⚠[/yellow]  No 8-K filings found in recent submissions"
            )

        for meta in filing_metas:
            acc_no: str = meta["accession_number"]
            date: str   = meta["filing_date"]
            url: Optional[str] = meta.get("document_url")

            if not url:
                err = "no primary document URL in submissions"
                _console.print(
                    f"       [red]✗[/red] {date}  "
                    f"[dim]{acc_no}[/dim]  {err}"
                )
                self.db.upsert_filing(
                    company_id=company_id,
                    accession_number=acc_no,
                    filing_date=date,
                    form_type=meta["form_type"],
                    period_of_report=meta.get("period_of_report") or None,
                    primary_document=meta.get("primary_document") or None,
                    document_url=None,
                    fetch_status="failed",
                    error_message=err,
                )
                filing_results.append(
                    FilingResult(acc_no, date, meta["form_type"], None, False, err)
                )
                continue

            try:
                raw_html, cleaned_text = self.sec.get_filing_content(url)
                word_count = len(cleaned_text.split()) if cleaned_text else 0

                self.db.upsert_filing(
                    company_id=company_id,
                    accession_number=acc_no,
                    filing_date=date,
                    form_type=meta["form_type"],
                    period_of_report=meta.get("period_of_report") or None,
                    primary_document=meta.get("primary_document") or None,
                    document_url=url,
                    raw_html=raw_html,
                    cleaned_text=cleaned_text,
                    word_count=word_count,
                    fetch_status="success",
                )
                _console.print(
                    f"       [green]✓[/green] {date}  "
                    f"[dim]{acc_no}[/dim]  "
                    f"[cyan]{word_count:,}[/cyan] words"
                )
                filing_results.append(
                    FilingResult(acc_no, date, meta["form_type"], word_count, True)
                )
                if latest_text is None and cleaned_text:
                    latest_text  = cleaned_text
                    latest_date  = date
                    latest_words = word_count
                    latest_url   = url

            except Exception as exc:
                err_str = str(exc)
                logger.error("Failed to fetch filing %s: %s", acc_no, exc)
                _console.print(
                    f"       [red]✗[/red] {date}  "
                    f"[dim]{acc_no}[/dim]  "
                    f"fetch failed: [red]{err_str[:80]}[/red]"
                )
                self.db.upsert_filing(
                    company_id=company_id,
                    accession_number=acc_no,
                    filing_date=date,
                    form_type=meta["form_type"],
                    period_of_report=meta.get("period_of_report") or None,
                    primary_document=meta.get("primary_document") or None,
                    document_url=url,
                    fetch_status="failed",
                    error_message=err_str,
                )
                filing_results.append(
                    FilingResult(acc_no, date, meta["form_type"], None, False, err_str)
                )

        # ── Step 4 : Earnings history ─────────────────────────────────
        _console.print(
            "\n [bold][3/4][/bold] Fetching earnings history (yfinance)..."
        )
        earnings_records: list[EarningsRecord] = self.market.get_earnings_history(ticker)
        stored_count = 0

        for record in earnings_records:
            try:
                self.db.upsert_earnings_date(
                    company_id=company_id,
                    earnings_date=record.earnings_date,
                    eps_estimate=record.eps_estimate,
                    eps_actual=record.eps_actual,
                    surprise_pct=record.surprise_pct,
                    revenue_estimate=record.revenue_estimate,
                    revenue_actual=record.revenue_actual,
                )
                stored_count += 1
            except Exception as exc:
                logger.warning("Failed to store earnings record %s: %s", record, exc)

        _console.print(
            f"       [green]✓[/green] {stored_count} earnings dates stored"
        )

        # ── Step 5 : Confirm persistence ─────────────────────────────
        elapsed = time.monotonic() - t0
        _console.print(
            f"\n [bold][4/4][/bold] Persisting to SQLite "
            f"[cyan]{self.db.db_path}[/cyan]"
        )
        _console.print(
            f"       [green]✓[/green] Done  "
            f"([dim]{elapsed:.2f}s[/dim])"
        )

        return IngestResult(
            ticker=ticker,
            cik=cik,
            company_name=yf_info.get("name") or company_name,
            db_path=self.db.db_path,
            filings=filing_results,
            earnings_count=stored_count,
            elapsed_seconds=elapsed,
            latest_filing_date=latest_date,
            latest_filing_words=latest_words,
            latest_filing_url=latest_url,
            latest_filing_text=latest_text,
        )
