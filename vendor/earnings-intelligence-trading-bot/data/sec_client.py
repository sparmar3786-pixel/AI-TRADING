"""
data/sec_client.py
------------------
SEC EDGAR API wrapper for the Earnings Intelligence System.

Responsibilities:
  - Resolve ticker symbols to SEC CIK numbers via the EDGAR ticker map
  - Fetch company submission metadata (filing history)
  - Download 8-K filing documents and extract clean plain text

SEC EDGAR fair-use policy:
  - Identify with a descriptive User-Agent containing contact info
  - Throttle requests to ≤ 10/second (we use 150 ms minimum gap)
  - See: https://www.sec.gov/privacy.htm#security
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_USER_AGENT = "Sebastian Caraballo scarabal@purdue.edu"
_RATE_LIMIT_MS = 150          # minimum milliseconds between any two SEC requests
_REQUEST_TIMEOUT_S = 30       # per-request timeout in seconds

_DATA_BASE_URL = "https://data.sec.gov"
_EDGAR_BASE_URL = "https://www.sec.gov"
_TICKER_MAP_URL = f"{_EDGAR_BASE_URL}/files/company_tickers.json"


# ---------------------------------------------------------------------------
# SEC EDGAR client
# ---------------------------------------------------------------------------

class SECClient:
    """
    Thin wrapper around the SEC EDGAR REST APIs.

    A single ``requests.Session`` is reused across calls so that keep-alive
    connections reduce latency.  A class-level timestamp enforces the 150 ms
    rate limit across all instances.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": _USER_AGENT,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json, text/html, */*",
            }
        )
        self._last_request_ts: float = 0.0
        # Cached ticker → zero-padded CIK map; populated on first use
        self._ticker_cik_map: Optional[dict[str, str]] = None

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """
        Block until at least ``_RATE_LIMIT_MS`` milliseconds have elapsed
        since the previous request.  SEC policy is max 10 req/s.
        """
        elapsed_ms = (time.monotonic() - self._last_request_ts) * 1000
        if elapsed_ms < _RATE_LIMIT_MS:
            time.sleep((_RATE_LIMIT_MS - elapsed_ms) / 1000)

    def _get(self, url: str, **kwargs) -> requests.Response:
        """
        Perform a rate-limited GET request and update the timestamp.

        Args:
            url:    Full URL to request.
            **kwargs: Extra arguments forwarded to ``requests.Session.get``.

        Returns:
            The ``requests.Response`` object.

        Raises:
            requests.HTTPError: On a 4xx/5xx response.
        """
        self._throttle()
        self._last_request_ts = time.monotonic()
        response = self._session.get(url, timeout=_REQUEST_TIMEOUT_S, **kwargs)
        response.raise_for_status()
        logger.debug("GET %s  [%s]", url, response.status_code)
        return response

    # ------------------------------------------------------------------
    # CIK resolution
    # ------------------------------------------------------------------

    def _load_ticker_map(self) -> dict[str, str]:
        """
        Download and cache the SEC EDGAR company tickers JSON.

        The file maps an integer offset to ``{"cik_str": int, "ticker": str,
        "title": str}``.  We invert it to a ``{TICKER: "0000000000"}`` dict.

        Returns:
            Dict mapping upper-case ticker to 10-digit zero-padded CIK string.
        """
        if self._ticker_cik_map is None:
            logger.debug("Loading EDGAR ticker→CIK map from %s", _TICKER_MAP_URL)
            data: dict = self._get(_TICKER_MAP_URL).json()
            self._ticker_cik_map = {
                entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
                for entry in data.values()
            }
            logger.debug("Loaded %d ticker entries", len(self._ticker_cik_map))
        return self._ticker_cik_map

    def get_cik(self, ticker: str) -> str:
        """
        Resolve a stock ticker to its SEC CIK (Central Index Key).

        Args:
            ticker: Stock ticker symbol, case-insensitive (e.g. ``"AAPL"``).

        Returns:
            10-digit zero-padded CIK string, e.g. ``"0000320193"``.

        Raises:
            ValueError: If the ticker is not found in the EDGAR company map.
        """
        mapping = self._load_ticker_map()
        cik = mapping.get(ticker.upper())
        if cik is None:
            raise ValueError(
                f"Ticker '{ticker.upper()}' not found in SEC EDGAR company list. "
                "Verify the ticker is listed on a US exchange."
            )
        return cik

    # ------------------------------------------------------------------
    # Submissions / filing metadata
    # ------------------------------------------------------------------

    def get_submissions(self, cik: str) -> dict:
        """
        Fetch the EDGAR submissions JSON for a company.

        Contains company metadata (name, SIC code, addresses) and a ``filings``
        key with parallel arrays describing every filing on record.

        Args:
            cik: 10-digit zero-padded CIK string.

        Returns:
            Parsed JSON dict from ``data.sec.gov/submissions/CIK{cik}.json``.
        """
        url = f"{_DATA_BASE_URL}/submissions/CIK{cik}.json"
        return self._get(url).json()

    def get_recent_filings(
        self,
        cik: str,
        form_type: str = "8-K",
        count: int = 5,
    ) -> list[dict]:
        """
        Return metadata for the most recent filings of a given form type.

        Parses the parallel arrays in ``submissions["filings"]["recent"]`` and
        constructs a direct URL to the primary document for each filing.

        Args:
            cik:       10-digit zero-padded CIK string.
            form_type: SEC form type to filter on (default ``"8-K"``).
            count:     Maximum number of filings to return.

        Returns:
            List of dicts, each containing:
              - ``accession_number``  – SEC accession number with dashes
              - ``filing_date``       – ISO date string
              - ``form_type``         – form type string
              - ``period_of_report``  – reporting period ISO date (may be empty)
              - ``primary_document``  – filename of main document
              - ``document_url``      – full URL to primary document (or None)
        """
        submissions = self.get_submissions(cik)
        recent: dict = submissions.get("filings", {}).get("recent", {})

        accessions   = recent.get("accessionNumber", [])
        dates        = recent.get("filingDate", [])
        forms        = recent.get("form", [])
        primary_docs = recent.get("primaryDocument", [])
        periods      = recent.get("reportDate", [])

        cik_int = int(cik)  # Archives URL uses non-padded integer CIK
        results: list[dict] = []

        for i, form in enumerate(forms):
            if form != form_type:
                continue
            if len(results) >= count:
                break

            acc_no = accessions[i]
            acc_nodash = acc_no.replace("-", "")
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""

            doc_url: Optional[str] = None
            if primary_doc:
                doc_url = (
                    f"{_EDGAR_BASE_URL}/Archives/edgar/data/"
                    f"{cik_int}/{acc_nodash}/{primary_doc}"
                )

            results.append(
                {
                    "accession_number": acc_no,
                    "filing_date": dates[i] if i < len(dates) else "",
                    "form_type": form,
                    "period_of_report": periods[i] if i < len(periods) else "",
                    "primary_document": primary_doc,
                    "document_url": doc_url,
                }
            )

        return results

    # ------------------------------------------------------------------
    # Filing content
    # ------------------------------------------------------------------

    def get_filing_content(self, url: str) -> tuple[str, str]:
        """
        Download an 8-K filing and return (raw_html, cleaned_text).

        If the primary document is an HTM/HTML file, the raw HTML is fetched,
        stripped of tags, and returned as clean plain text suitable for LLM
        analysis.  Non-HTML responses (PDF, XBRL XML, plain text) are handled
        gracefully by falling back to the raw content as the "cleaned" text.

        Args:
            url: Direct URL to the filing document.

        Returns:
            Tuple of ``(raw_html, cleaned_text)``.

        Raises:
            requests.HTTPError: On HTTP errors (caller should catch).
            requests.Timeout:   If the request exceeds ``_REQUEST_TIMEOUT_S``.
        """
        response = self._get(url)
        content_type = response.headers.get("Content-Type", "").lower()
        raw = response.text

        if "html" in content_type or url.lower().endswith((".htm", ".html")):
            cleaned = self._clean_html(raw)
        elif "pdf" in content_type or url.lower().endswith(".pdf"):
            logger.warning("Primary document at %s is a PDF; skipping text extraction.", url)
            cleaned = "[PDF document — text extraction not supported in Phase 1]"
        else:
            # Plain text or XBRL XML — strip tags just in case
            cleaned = self._clean_html(raw)

        return raw, cleaned

    # ------------------------------------------------------------------
    # HTML cleaning
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_html(html_content: str) -> str:
        """
        Extract clean, LLM-ready plain text from an SEC filing HTML document.

        Steps:
          1. Parse with BeautifulSoup (html.parser, no lxml dependency risk)
          2. Remove non-content elements: script, style, meta, link, noscript
          3. Unwrap iXBRL/XBRL namespace tags (``ix:nonNumeric`` etc.) while
             preserving their text content
          4. Extract text with newline separators between block elements
          5. Normalise whitespace: collapse intra-line runs, remove blank lines,
             deduplicate consecutive identical lines

        Args:
            html_content: Raw HTML string from an SEC EDGAR document.

        Returns:
            Clean plain text string.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove entirely non-content elements
        for tag in soup.find_all(
            ["script", "style", "meta", "link", "noscript", "head"]
        ):
            tag.decompose()

        # Unwrap iXBRL / XBRL namespace tags (e.g. ix:nonNumeric, ix:nonFraction)
        # Keep their text content so numbers aren't dropped
        for tag in soup.find_all(
            lambda t: t.name and ":" in t.name  # type: ignore[union-attr]
        ):
            tag.unwrap()

        # Extract text, using newline as the separator between elements
        raw_text = soup.get_text(separator="\n")

        # Normalise whitespace within each line
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]

        # Remove blank lines, deduplicate consecutive identical lines
        cleaned_lines: list[str] = []
        prev: Optional[str] = None
        for line in lines:
            if line and line != prev:
                cleaned_lines.append(line)
                prev = line

        # Collapse runs of more than 2 consecutive newlines → 2 (paragraph breaks)
        result = "\n".join(cleaned_lines)
        result = re.sub(r"\n{3,}", "\n\n", result)

        return result.strip()
