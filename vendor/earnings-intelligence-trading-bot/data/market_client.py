"""
data/market_client.py
---------------------
yfinance wrapper for the Earnings Intelligence System.

Fetches:
  - Historical earnings dates with EPS estimates, actuals, and surprise %
  - Designed to be extended in Phase 2 with price / options data
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------

@dataclass
class EarningsRecord:
    """
    Single earnings event for a company.

    Fields mirror the ``earnings_dates`` SQLite table columns so that the
    fetcher can pass them straight through to ``Database.upsert_earnings_date``.
    """

    earnings_date: datetime
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    surprise_pct: Optional[float] = None
    revenue_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def has_actuals(self) -> bool:
        """Return True if actual EPS data is present and non-NaN."""
        return self.eps_actual is not None

    def __repr__(self) -> str:
        return (
            f"EarningsRecord("
            f"date={self.earnings_date.date()}, "
            f"est={self.eps_estimate}, "
            f"act={self.eps_actual}, "
            f"surp={self.surprise_pct}%)"
        )


# ---------------------------------------------------------------------------
# Market client
# ---------------------------------------------------------------------------

class MarketClient:
    """
    Wrapper around yfinance for earnings and market data.

    All methods return empty lists / None on failure rather than raising, so
    a yfinance outage does not abort the full ingestion pipeline.
    """

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        """
        Convert *value* to float, returning ``None`` for NaN / None / non-numeric.

        Args:
            value: Any value from a pandas DataFrame cell.

        Returns:
            Finite float or ``None``.
        """
        if value is None:
            return None
        try:
            f = float(value)  # type: ignore[arg-type]
            return None if math.isnan(f) or math.isinf(f) else f
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _strip_tz(dt: object) -> datetime:
        """
        Remove timezone info from a pandas Timestamp / datetime.

        SQLite stores datetimes as naive strings; timezone-aware objects would
        cause ``isoformat()`` to include an offset we don't want.

        Args:
            dt: A ``pandas.Timestamp`` or ``datetime`` object.

        Returns:
            Timezone-naive ``datetime``.
        """
        if isinstance(dt, pd.Timestamp):
            return dt.to_pydatetime().replace(tzinfo=None)
        if isinstance(dt, datetime) and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt  # type: ignore[return-value]

    def get_earnings_history(self, ticker: str) -> list[EarningsRecord]:
        """
        Fetch historical earnings dates and EPS data via yfinance.

        Uses ``Ticker.earnings_dates`` which returns up to 4 years of
        quarterly earnings events (past and near-future estimates).

        Column names in the returned DataFrame:
          - ``EPS Estimate``   – analyst consensus
          - ``Reported EPS``   – actual reported EPS
          - ``Surprise(%)``    – percentage surprise

        Args:
            ticker: Stock ticker symbol (case-insensitive).

        Returns:
            List of ``EarningsRecord`` objects sorted newest-first.
            Returns an empty list if yfinance fails or returns no data.
        """
        ticker_upper = ticker.upper()
        logger.debug("Fetching earnings history for %s via yfinance", ticker_upper)

        try:
            t = yf.Ticker(ticker_upper)
            df: Optional[pd.DataFrame] = t.earnings_dates
        except Exception as exc:
            logger.warning(
                "yfinance raised an exception for %s: %s", ticker_upper, exc
            )
            return []

        if df is None or df.empty:
            logger.warning("yfinance returned no earnings data for %s", ticker_upper)
            return []

        records: list[EarningsRecord] = []
        for date_idx, row in df.iterrows():
            try:
                earnings_dt = self._strip_tz(date_idx)
                record = EarningsRecord(
                    earnings_date=earnings_dt,
                    eps_estimate=self._safe_float(row.get("EPS Estimate")),
                    eps_actual=self._safe_float(row.get("Reported EPS")),
                    surprise_pct=self._safe_float(row.get("Surprise(%)")),
                )
                records.append(record)
            except Exception as exc:
                logger.warning(
                    "Skipping malformed earnings row for %s on %s: %s",
                    ticker_upper,
                    date_idx,
                    exc,
                )

        logger.debug(
            "Retrieved %d earnings records for %s", len(records), ticker_upper
        )
        return records

    def get_company_info(self, ticker: str) -> dict:
        """
        Fetch basic company metadata (sector, exchange, name) via yfinance.

        Used to enrich the ``companies`` table beyond what SEC EDGAR provides.
        Returns an empty dict on any failure.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Dict with keys ``"sector"``, ``"exchange"``, ``"name"`` where available.
        """
        try:
            info = yf.Ticker(ticker.upper()).info or {}
            return {
                "sector": info.get("sector"),
                "exchange": info.get("exchange"),
                "name": info.get("longName") or info.get("shortName"),
            }
        except Exception as exc:
            logger.warning(
                "yfinance info lookup failed for %s: %s", ticker.upper(), exc
            )
            return {}
