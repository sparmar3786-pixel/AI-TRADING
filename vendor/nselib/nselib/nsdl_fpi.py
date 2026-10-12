from __future__ import annotations

import atexit
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import StringIO
import os
import re

import pandas as pd
import requests

from nselib.libutil import default_header

REPORT_DATE_FORMAT = "%d-%b-%Y"
PRODUCTION_BASE_URL = "https://www.fpi.nsdl.co.in/web/Reports"
PILOT_BASE_URL = "https://pilot.fpi.nsdl.co.in/Reports"
REQUEST_BASE_URLS = [PILOT_BASE_URL, PRODUCTION_BASE_URL]
LATEST_PAGE = "Latest.aspx"
ARCHIVE_PAGE = "Archive.aspx"
ARCHIVE_HIDDEN_FIELDS = ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")
BROWSER_EXECUTABLE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
BROWSER_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
]
BROWSER_NAVIGATION_OPTIONS = {"waitUntil": "networkidle2", "timeout": 60000}
BROWSER_USER_AGENT = default_header.get(
    "User-Agent",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
)

INVESTMENT_COLUMNS = [
    "REPORT_DATE",
    "ASSET_CLASS",
    "INVESTMENT_ROUTE",
    "GROSS_PURCHASES_RS_CR",
    "GROSS_SALES_RS_CR",
    "NET_INVESTMENT_RS_CR",
    "NET_INVESTMENT_USD_MN",
    "USD_INR_CONVERSION",
]

DERIVATIVE_COLUMNS = [
    "REPORT_DATE",
    "DERIVATIVE_PRODUCT",
    "BUY_CONTRACTS",
    "BUY_AMOUNT_CR",
    "SELL_CONTRACTS",
    "SELL_AMOUNT_CR",
    "OPEN_INTEREST_CONTRACTS",
    "OPEN_INTEREST_AMOUNT_CR",
]

DAILY_DERIVATIVE_PRODUCTS = {
    "Index Futures",
    "Index Options",
    "Stock Futures",
    "Stock Options",
    "Interest Rate Futures",
    "Currency Futures",
    "Currency Options",
    "Commodity Futures",
    "Commodity Options",
}


@dataclass
class NSDLFPIReportBundle:
    investment: pd.DataFrame
    derivative: pd.DataFrame
    source_page: str
    as_of_date: date | None = None


def _empty_investment_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=INVESTMENT_COLUMNS)


def _empty_derivative_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=DERIVATIVE_COLUMNS)


def _coerce_trade_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value, dayfirst=True, errors="raise").date()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid NSDL trade date: {value}") from exc


def _flatten_column_name(column: object) -> str:
    if isinstance(column, tuple):
        parts = [
            str(part).strip()
            for part in column
            if part is not None
            and str(part).strip()
            and not str(part).strip().lower().startswith("unnamed:")
        ]
        return " | ".join(parts)
    return str(column).strip()


def _normalize_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _parse_numeric(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-", "--"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "")
    text = text.replace("Rs.", "").replace("Rs", "").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _find_browser_executable() -> str | None:
    for candidate in BROWSER_EXECUTABLE_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


def _extract_hidden_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for field_name in ARCHIVE_HIDDEN_FIELDS:
        match = re.search(
            rf'name="{field_name}"\s+id="{field_name}"\s+value="([^"]*)"',
            html,
        )
        fields[field_name] = match.group(1) if match else ""
    return fields


def _read_tables(html: str) -> list[pd.DataFrame]:
    try:
        return pd.read_html(StringIO(html))
    except ValueError:
        return []


def _classify_table(table: pd.DataFrame) -> str | None:
    column_names = [_flatten_column_name(column).lower() for column in table.columns]
    if any("investment route" in column_name for column_name in column_names):
        return "investment"
    if any("derivative products" in column_name for column_name in column_names):
        return "derivative"
    return None


def _parse_investment_table(table: pd.DataFrame) -> pd.DataFrame:
    frame = table.copy()
    frame.columns = [_flatten_column_name(column) for column in frame.columns]
    frame = frame.dropna(how="all").reset_index(drop=True)
    rename_map: dict[str, str] = {}
    for column_name in frame.columns:
        normalized = column_name.lower()
        if "reporting date" in normalized:
            rename_map[column_name] = "REPORT_DATE"
        elif "investment route" in normalized:
            rename_map[column_name] = "INVESTMENT_ROUTE"
        elif "gross purchases" in normalized:
            rename_map[column_name] = "GROSS_PURCHASES_RS_CR"
        elif "gross sales" in normalized:
            rename_map[column_name] = "GROSS_SALES_RS_CR"
        elif "net investment" in normalized and "us($" not in normalized:
            rename_map[column_name] = "NET_INVESTMENT_RS_CR"
        elif "net investment us($" in normalized:
            rename_map[column_name] = "NET_INVESTMENT_USD_MN"
        elif "conversion" in normalized:
            rename_map[column_name] = "USD_INR_CONVERSION"
        elif "debt" in normalized and "equity" in normalized:
            rename_map[column_name] = "ASSET_CLASS"
    frame = frame.rename(columns=rename_map)
    available_columns = [column_name for column_name in INVESTMENT_COLUMNS if column_name in frame.columns]
    if not available_columns:
        return _empty_investment_frame()
    frame = frame[available_columns].copy()
    for column_name in INVESTMENT_COLUMNS:
        if column_name not in frame.columns:
            frame[column_name] = None
    parsed_dates = pd.to_datetime(frame["REPORT_DATE"], format=REPORT_DATE_FORMAT, errors="coerce").ffill()
    frame["REPORT_DATE"] = parsed_dates.dt.date
    frame["ASSET_CLASS"] = frame["ASSET_CLASS"].apply(_normalize_text)
    frame["INVESTMENT_ROUTE"] = frame["INVESTMENT_ROUTE"].apply(_normalize_text)
    for column_name in [
        "GROSS_PURCHASES_RS_CR",
        "GROSS_SALES_RS_CR",
        "NET_INVESTMENT_RS_CR",
        "NET_INVESTMENT_USD_MN",
        "USD_INR_CONVERSION",
    ]:
        frame[column_name] = frame[column_name].apply(_parse_numeric)
    frame = frame.dropna(subset=["REPORT_DATE", "ASSET_CLASS"]).copy()
    frame = frame[frame["ASSET_CLASS"].str.lower() != "note"].copy()
    frame = frame[frame["USD_INR_CONVERSION"].notna()].copy()
    frame = frame[INVESTMENT_COLUMNS].drop_duplicates(
        subset=["REPORT_DATE", "ASSET_CLASS", "INVESTMENT_ROUTE"],
        keep="first",
    ).reset_index(drop=True)
    return frame


def _parse_derivative_table(table: pd.DataFrame) -> pd.DataFrame:
    frame = table.copy()
    frame.columns = [_flatten_column_name(column) for column in frame.columns]
    frame = frame.dropna(how="all").reset_index(drop=True)
    rename_map: dict[str, str] = {}
    for column_name in frame.columns:
        normalized = column_name.lower()
        if "reporting date" in normalized:
            rename_map[column_name] = "REPORT_DATE"
        elif "derivative products" in normalized:
            rename_map[column_name] = "DERIVATIVE_PRODUCT"
        elif "buy" in normalized and "no. of contracts" in normalized:
            rename_map[column_name] = "BUY_CONTRACTS"
        elif "buy" in normalized and "amount in crore" in normalized:
            rename_map[column_name] = "BUY_AMOUNT_CR"
        elif "sell" in normalized and "no. of contracts" in normalized:
            rename_map[column_name] = "SELL_CONTRACTS"
        elif "sell" in normalized and "amount in crore" in normalized:
            rename_map[column_name] = "SELL_AMOUNT_CR"
        elif "open interest" in normalized and "no. of contracts" in normalized:
            rename_map[column_name] = "OPEN_INTEREST_CONTRACTS"
        elif "open interest" in normalized and "amount in crore" in normalized:
            rename_map[column_name] = "OPEN_INTEREST_AMOUNT_CR"
    frame = frame.rename(columns=rename_map)
    available_columns = [column_name for column_name in DERIVATIVE_COLUMNS if column_name in frame.columns]
    if not available_columns:
        return _empty_derivative_frame()
    frame = frame[available_columns].copy()
    for column_name in DERIVATIVE_COLUMNS:
        if column_name not in frame.columns:
            frame[column_name] = None
    parsed_dates = pd.to_datetime(frame["REPORT_DATE"], format=REPORT_DATE_FORMAT, errors="coerce").ffill()
    frame["REPORT_DATE"] = parsed_dates.dt.date
    frame["DERIVATIVE_PRODUCT"] = frame["DERIVATIVE_PRODUCT"].apply(_normalize_text)
    frame["DERIVATIVE_PRODUCT"] = (
        frame["DERIVATIVE_PRODUCT"]
        .fillna("")
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.title()
    )
    for column_name in [
        "BUY_CONTRACTS",
        "BUY_AMOUNT_CR",
        "SELL_CONTRACTS",
        "SELL_AMOUNT_CR",
        "OPEN_INTEREST_CONTRACTS",
        "OPEN_INTEREST_AMOUNT_CR",
    ]:
        frame[column_name] = frame[column_name].apply(_parse_numeric)
    frame = frame.dropna(subset=["REPORT_DATE", "DERIVATIVE_PRODUCT"]).copy()
    frame = frame[frame["DERIVATIVE_PRODUCT"].isin(DAILY_DERIVATIVE_PRODUCTS)].copy()
    frame = frame[DERIVATIVE_COLUMNS].drop_duplicates(
        subset=["REPORT_DATE", "DERIVATIVE_PRODUCT"],
        keep="first",
    ).reset_index(drop=True)
    return frame


def _parse_report_bundle(html: str, source_page: str, as_of_date: date | None) -> NSDLFPIReportBundle:
    investment = _empty_investment_frame()
    derivative = _empty_derivative_frame()
    for table in _read_tables(html):
        table_type = _classify_table(table)
        if table_type == "investment":
            investment = _parse_investment_table(table)
        elif table_type == "derivative":
            derivative = _parse_derivative_table(table)
    return NSDLFPIReportBundle(
        investment=investment,
        derivative=derivative,
        source_page=source_page,
        as_of_date=as_of_date,
    )


def _max_bundle_report_date(bundle: NSDLFPIReportBundle) -> date | None:
    dates: list[date] = []
    for frame in (bundle.investment, bundle.derivative):
        if frame.empty or "REPORT_DATE" not in frame.columns:
            continue
        valid = [value for value in frame["REPORT_DATE"].tolist() if isinstance(value, date)]
        if valid:
            dates.append(max(valid))
    if not dates:
        return None
    return max(dates)


class NSDLProductionBrowser:
    def __init__(self) -> None:
        self.executable_path = _find_browser_executable()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._browser = None
        self._atexit_registered = False

    @property
    def available(self) -> bool:
        return bool(self.executable_path)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _run(self, coroutine):
        loop = self._ensure_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coroutine)

    async def _ensure_browser(self):
        if not self.available or not self.executable_path:
            raise FileNotFoundError("No supported Edge/Chrome executable was found for NSDL production scraping")
        if self._browser is not None:
            process = getattr(self._browser, "process", None)
            if process is None or process.poll() is None:
                return self._browser
        from pyppeteer import launch

        self._browser = await launch(
            headless=True,
            executablePath=self.executable_path,
            args=BROWSER_LAUNCH_ARGS,
            handleSIGINT=False,
            handleSIGTERM=False,
            handleSIGHUP=False,
        )
        if not self._atexit_registered:
            atexit.register(self.close)
            self._atexit_registered = True
        return self._browser

    async def _new_page(self, url: str):
        browser = await self._ensure_browser()
        page = await browser.newPage()
        await page.setUserAgent(BROWSER_USER_AGENT)
        await page.goto(url, BROWSER_NAVIGATION_OPTIONS)
        return page

    async def _latest_html(self) -> str:
        page = await self._new_page(f"{PRODUCTION_BASE_URL}/{LATEST_PAGE}")
        try:
            return await page.content()
        finally:
            await page.close()

    async def _archive_html(self, trade_date: date) -> str:
        page = await self._new_page(f"{PRODUCTION_BASE_URL}/{ARCHIVE_PAGE}")
        try:
            trade_date_text = trade_date.strftime(REPORT_DATE_FORMAT)
            await page.evaluate(
                """(dateValue) => {
                    const txtDate = document.querySelector('#txtDate');
                    const hiddenDate = document.querySelector('#hdnDate');
                    if (!txtDate || !hiddenDate) {
                        throw new Error('NSDL archive date controls were not found');
                    }
                    txtDate.disabled = false;
                    txtDate.value = dateValue;
                    hiddenDate.value = dateValue;
                }""",
                trade_date_text,
            )
            await asyncio.gather(
                page.waitForNavigation(BROWSER_NAVIGATION_OPTIONS),
                page.click("#btnSubmit1"),
            )
            return await page.content()
        finally:
            await page.close()

    def latest_html(self) -> str:
        return self._run(self._latest_html())

    def archive_html(self, trade_date: date) -> str:
        return self._run(self._archive_html(trade_date))

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._run(self._browser.close())
        except Exception:
            pass
        finally:
            self._browser = None
        try:
            if self._loop is not None and not self._loop.is_closed():
                self._loop.close()
        except Exception:
            pass
        finally:
            self._loop = None


class NSDLFPIClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(default_header)
        self.browser = NSDLProductionBrowser()
        self._request_base_url: str | None = None
        self._archive_payload_fields: dict[str, str] | None = None

    def _resolve_request_base_url(self, page_name: str = LATEST_PAGE) -> str:
        if self._request_base_url is not None:
            return self._request_base_url
        last_error: Exception | None = None
        for base_url in REQUEST_BASE_URLS:
            try:
                response = self.session.get(f"{base_url}/{page_name}", timeout=60)
                response.raise_for_status()
                if "NSDL" not in response.text or "FPI" not in response.text:
                    continue
                self._request_base_url = base_url
                if page_name == ARCHIVE_PAGE:
                    self._archive_payload_fields = _extract_hidden_fields(response.text)
                return self._request_base_url
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise FileNotFoundError(f"Unable to reach NSDL FPI reports page: {last_error}")

    def _get_request_page(self, page_name: str) -> str:
        base_url = self._resolve_request_base_url(page_name)
        response = self.session.get(f"{base_url}/{page_name}", timeout=60)
        response.raise_for_status()
        return response.text

    def _archive_request_fields(self, refresh: bool = False) -> dict[str, str]:
        if self._archive_payload_fields is not None and not refresh:
            return self._archive_payload_fields
        html = self._get_request_page(ARCHIVE_PAGE)
        fields = _extract_hidden_fields(html)
        if not all(fields.values()):
            raise FileNotFoundError("Unable to prepare NSDL archive request")
        self._archive_payload_fields = fields
        return fields

    def _get_latest_html(self) -> tuple[str, str]:
        errors: list[str] = []
        if self.browser.available:
            try:
                return self.browser.latest_html(), PRODUCTION_BASE_URL
            except Exception as exc:  # noqa: BLE001
                errors.append(f"production_browser: {exc}")
        try:
            return self._get_request_page(LATEST_PAGE), self._resolve_request_base_url(LATEST_PAGE)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"request_fallback: {exc}")
        raise FileNotFoundError("Unable to fetch NSDL latest page :: " + " | ".join(errors))

    def _get_archive_html(self, trade_date: date) -> tuple[str, str]:
        errors: list[str] = []
        if self.browser.available:
            try:
                return self.browser.archive_html(trade_date), PRODUCTION_BASE_URL
            except Exception as exc:  # noqa: BLE001
                errors.append(f"production_browser: {exc}")

        try:
            fields = self._archive_request_fields()
            payload = {
                "__EVENTTARGET": "btnSubmit1",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": fields["__VIEWSTATE"],
                "__VIEWSTATEGENERATOR": fields["__VIEWSTATEGENERATOR"],
                "__EVENTVALIDATION": fields["__EVENTVALIDATION"],
                "txtDate": trade_date.strftime(REPORT_DATE_FORMAT),
                "hdnDate": trade_date.strftime(REPORT_DATE_FORMAT),
                "HdnValexceldata": "",
                "hdnFlag": "",
            }
            base_url = self._resolve_request_base_url(ARCHIVE_PAGE)
            response = self.session.post(
                f"{base_url}/{ARCHIVE_PAGE}",
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.text, base_url
        except Exception as exc:  # noqa: BLE001
            errors.append(f"request_fallback: {exc}")
            try:
                self._archive_request_fields(refresh=True)
            except Exception:
                pass
        raise FileNotFoundError("Unable to fetch NSDL archive page :: " + " | ".join(errors))

    def latest_bundle(self) -> NSDLFPIReportBundle:
        html, source_base = self._get_latest_html()
        source_page = "latest_production_browser" if source_base == PRODUCTION_BASE_URL else "latest_request_fallback"
        bundle = _parse_report_bundle(html, source_page=source_page, as_of_date=None)
        bundle.as_of_date = _max_bundle_report_date(bundle)
        if bundle.investment.empty and bundle.derivative.empty:
            raise FileNotFoundError("NSDL latest page did not contain investment or derivative data")
        return bundle

    def archive_month_bundle(self, trade_date: date | datetime | str, max_lookback_days: int = 10) -> NSDLFPIReportBundle:
        requested_date = _coerce_trade_date(trade_date)
        current_date = requested_date
        month_key = (requested_date.year, requested_date.month)
        last_error: Exception | None = None
        for _ in range(max_lookback_days + 1):
            if (current_date.year, current_date.month) != month_key:
                break
            try:
                html, source_base = self._get_archive_html(current_date)
                if "No Data To Display" not in html:
                    source_page = (
                        "archive_production_browser" if source_base == PRODUCTION_BASE_URL else "archive_request_fallback"
                    )
                    bundle = _parse_report_bundle(html, source_page=source_page, as_of_date=current_date)
                    if not bundle.investment.empty or not bundle.derivative.empty:
                        return bundle
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                try:
                    self._archive_request_fields(refresh=True)
                except Exception:  # noqa: BLE001
                    pass
            current_date -= timedelta(days=1)
        if last_error is not None:
            raise FileNotFoundError(
                f"NSDL archive data not available for month ending {requested_date.strftime(REPORT_DATE_FORMAT)}: {last_error}"
            )
        raise FileNotFoundError(
            f"NSDL archive data not available for month ending {requested_date.strftime(REPORT_DATE_FORMAT)}"
        )


def fetch_nsdl_fpi_latest_bundle() -> NSDLFPIReportBundle:
    return NSDLFPIClient().latest_bundle()


def fetch_nsdl_fpi_month_bundle(trade_date: date | datetime | str) -> NSDLFPIReportBundle:
    return NSDLFPIClient().archive_month_bundle(trade_date)


def fetch_nsdl_fpi_latest_investment_activity() -> pd.DataFrame:
    return fetch_nsdl_fpi_latest_bundle().investment.copy()


def fetch_nsdl_fpi_latest_derivative_activity() -> pd.DataFrame:
    return fetch_nsdl_fpi_latest_bundle().derivative.copy()


def fetch_nsdl_fpi_investment_activity(trade_date: date | datetime | str) -> pd.DataFrame:
    requested_date = _coerce_trade_date(trade_date)
    frame = fetch_nsdl_fpi_month_bundle(requested_date).investment
    frame = frame[frame["REPORT_DATE"] == requested_date].copy().reset_index(drop=True)
    if frame.empty:
        raise FileNotFoundError(f"NSDL investment activity not found for {requested_date.strftime(REPORT_DATE_FORMAT)}")
    return frame


def fetch_nsdl_fpi_derivative_activity(trade_date: date | datetime | str) -> pd.DataFrame:
    requested_date = _coerce_trade_date(trade_date)
    frame = fetch_nsdl_fpi_month_bundle(requested_date).derivative
    frame = frame[frame["REPORT_DATE"] == requested_date].copy().reset_index(drop=True)
    if frame.empty:
        raise FileNotFoundError(f"NSDL derivative activity not found for {requested_date.strftime(REPORT_DATE_FORMAT)}")
    return frame
