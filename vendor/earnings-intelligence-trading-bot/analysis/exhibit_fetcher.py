"""
analysis/exhibit_fetcher.py
---------------------------
Fetches Exhibit 99.1 (the earnings press release) from an SEC 8-K filing.

Why Exhibit 99.1?
  The primary 8-K document is a cover page with legal boilerplate.
  The actual earnings data — revenue, EPS, guidance — lives in Exhibit 99.1,
  the press release that gets attached to the filing.

Flow:
  1. Build filing index URL from accession number + CIK
  2. Fetch the index HTML and parse the document table
  3. Locate the row whose Type column contains "EX-99.1"
  4. Download that document and return its cleaned text

SEC EDGAR index URL pattern:
  https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{acc_no}-index.htm
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from data.sec_client import SECClient

logger = logging.getLogger(__name__)

_EDGAR_BASE_URL = "https://www.sec.gov"

# Exhibit type strings to accept (in priority order)
_EXHIBIT_TYPES = ["EX-99.1", "EX-99"]


@dataclass
class ExhibitLocation:
    """
    Outcome of the cheap index-page lookup, before any exhibit download.

    ``status`` values:
      * ``"ok"``          exhibit row found; ``url`` is set
      * ``"no_exhibit"``  index parsed fine but the filing has no EX-99.1 —
                          a permanent property of the filing (not an earnings
                          8-K), safe to remember and never re-check
      * ``"error"``       index fetch/parse failed — transient, retry later
    """

    status: str
    url: Optional[str] = None


class ExhibitFetcher:
    """
    Fetches Exhibit 99.1 content from SEC 8-K filings.

    Uses the filing index page to locate the press-release exhibit, then
    downloads and cleans its text for LLM analysis.  Re-uses the existing
    SECClient session and rate limiter so no additional throttling is needed.

    Args:
        sec_client: An initialized SECClient instance.  A new one is created
                    if not provided.
    """

    def __init__(self, sec_client: Optional[SECClient] = None) -> None:
        self._sec = sec_client or SECClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def locate(self, accession_number: str, cik: str) -> ExhibitLocation:
        """
        Find the Exhibit 99.1 URL using only the filing index page (one
        throttled SEC request, no exhibit download). Lets callers decide
        whether to spend a download/LLM call, and lets the pipeline mark
        exhibit-less filings permanently.

        Args:
            accession_number: SEC accession number with dashes.
            cik:              10-digit zero-padded CIK string.

        Returns:
            :class:`ExhibitLocation` with status ok / no_exhibit / error.
        """
        return self._find_exhibit_url(accession_number, cik)

    def download(self, exhibit_url: str) -> Optional[str]:
        """
        Download and clean an exhibit located by :meth:`locate`.

        Args:
            exhibit_url: Absolute URL returned in ``ExhibitLocation.url``.

        Returns:
            Cleaned plain text, or ``None`` on download failure / empty body.
        """
        logger.info("Fetching Exhibit 99.1 from %s", exhibit_url)
        try:
            _, cleaned_text = self._sec.get_filing_content(exhibit_url)
            return cleaned_text if cleaned_text.strip() else None
        except Exception as exc:
            logger.error("Failed to fetch exhibit at %s: %s", exhibit_url, exc)
            return None

    def get_exhibit_text(
        self,
        accession_number: str,
        cik: str,
    ) -> Optional[str]:
        """
        Fetch and clean the text of Exhibit 99.1 for an 8-K filing
        (locate + download in one call, kept for convenience).

        Args:
            accession_number: SEC accession number with dashes
                              (e.g. ``"0000320193-24-000123"``).
            cik:              10-digit zero-padded CIK string.

        Returns:
            Cleaned plain text of the exhibit, or ``None`` if the exhibit is
            not present in the filing index or the download fails.
        """
        location = self.locate(accession_number, cik)
        if location.status != "ok" or not location.url:
            logger.warning(
                "No Exhibit 99.1 found in filing index for accession %s",
                accession_number,
            )
            return None
        return self.download(location.url)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_exhibit_url(
        self,
        accession_number: str,
        cik: str,
    ) -> ExhibitLocation:
        """
        Fetch the filing index page and locate the EX-99.1 row.

        The EDGAR filing index HTML contains a ``<table>`` with rows for
        every document in the filing.  Each row has columns:
          Seq | Description | Document | Type | Size

        We scan for a row whose ``Type`` column matches one of the
        ``_EXHIBIT_TYPES`` strings.

        Args:
            accession_number: Accession number with dashes.
            cik:              Zero-padded CIK string.

        Returns:
            :class:`ExhibitLocation` — status "ok" with the absolute exhibit
            URL, "no_exhibit" when the index parsed but has no matching row,
            or "error" when the index fetch itself failed (retryable).
        """
        cik_int = int(cik)
        acc_nodash = accession_number.replace("-", "")
        index_url = (
            f"{_EDGAR_BASE_URL}/Archives/edgar/data/"
            f"{cik_int}/{acc_nodash}/{accession_number}-index.htm"
        )

        logger.debug("Fetching filing index: %s", index_url)
        try:
            response = self._sec._get(index_url)
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            logger.error("Failed to fetch filing index %s: %s", index_url, exc)
            return ExhibitLocation(status="error")

        # Iterate over all table rows; the document table has 4-5 columns.
        # Column index 3 = Type, column index 2 = Document (with <a> link).
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            type_text = cells[3].get_text(strip=True).upper()

            for exhibit_type in _EXHIBIT_TYPES:
                if exhibit_type in type_text:
                    link = cells[2].find("a")
                    if link and link.get("href"):
                        href = link["href"]
                        if href.startswith("http"):
                            return ExhibitLocation(status="ok", url=href)
                        # Relative path → prepend base URL
                        return ExhibitLocation(
                            status="ok", url=f"{_EDGAR_BASE_URL}{href}"
                        )
                    break  # Type matched but no link; keep scanning rows

        logger.warning(
            "EX-99.1 not found in index table for accession %s (CIK %s)",
            accession_number,
            cik,
        )
        return ExhibitLocation(status="no_exhibit")
