from __future__ import annotations

import io
import json
import re
from datetime import date
from urllib.parse import urljoin

import pandas as pd
import requests

from nselib.libutil import NSEdataNotFound, default_header

AMFI_MONTHLY_PAGE_URL = "https://www.amfiindia.com/research-information/amfi-monthly"
_AMFI_REPORT_LINK_PATTERN = re.compile(
    r"/spages/am([a-z]+)(\d{4})repo(?:revised)?\.(pdf|xls|xlsx|htm|html)$",
    re.IGNORECASE,
)
_MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_DEFAULT_FILE_TYPE_PRIORITY = ("pdf", "xls", "xlsx", "html", "htm")
_OUTPUT_COLUMNS = [
    "REPORT_MONTH",
    "PERIOD_LABEL",
    "SOURCE_URL",
    "SOURCE_FILE_TYPE",
    "SECTION_NAME",
    "TABLE_INDEX",
    "ROW_INDEX",
    "ROW_JSON",
    "ROW_TEXT",
]


def _amfi_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(default_header)
    return session


def _normalize_report_month(value: str | date) -> date:
    parsed = pd.to_datetime(value, dayfirst=True, errors="raise").date()
    return parsed.replace(day=1)


def _empty_output_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_OUTPUT_COLUMNS)


def _extract_link_records(page_html: str) -> list[dict[str, object]]:
    hrefs = set(re.findall(r'href=["\']([^"\']+)["\']', page_html, flags=re.IGNORECASE))
    records: list[dict[str, object]] = []
    for href in hrefs:
        normalized_url = urljoin(AMFI_MONTHLY_PAGE_URL, href.strip())
        match = _AMFI_REPORT_LINK_PATTERN.search(normalized_url)
        if match is None:
            continue
        month_token = match.group(1).lower()
        month_value = _MONTH_MAP.get(month_token)
        if month_value is None:
            continue
        year_value = int(match.group(2))
        file_type = match.group(3).lower()
        report_month = date(year_value, month_value, 1)
        records.append(
            {
                "REPORT_MONTH": report_month,
                "PERIOD_LABEL": report_month.strftime("%b-%Y"),
                "REPORT_YEAR": year_value,
                "REPORT_MONTH_NUM": month_value,
                "FILE_TYPE": file_type,
                "IS_REVISED": "reporevised." in normalized_url.lower(),
                "SOURCE_URL": normalized_url,
            }
        )
    return records


def _priority_rank(file_type: object, file_type_priority: tuple[str, ...]) -> int:
    normalized = str(file_type).strip().lower()
    try:
        return file_type_priority.index(normalized)
    except ValueError:
        return len(file_type_priority)


def _preferred_links(links_frame: pd.DataFrame, file_type_priority: tuple[str, ...]) -> pd.DataFrame:
    if links_frame.empty:
        return links_frame
    ordered = links_frame.copy()
    ordered["__priority"] = ordered["FILE_TYPE"].apply(lambda value: _priority_rank(value, file_type_priority))
    ordered = ordered.sort_values(
        by=["REPORT_MONTH", "__priority", "IS_REVISED", "SOURCE_URL"],
        ascending=[True, True, False, True],
    )
    ordered = ordered.drop_duplicates(subset=["REPORT_MONTH"], keep="first").reset_index(drop=True)
    return ordered.drop(columns=["__priority"])


def _download_report_content(source_url: str) -> bytes:
    session = _amfi_session()
    response = session.get(source_url, timeout=90)
    if response.status_code != 200:
        raise NSEdataNotFound(f"AMFI report URL not reachable: {source_url} (status={response.status_code})")
    return response.content


def _coerce_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text_value = str(value).replace("\u00a0", " ").strip()
    if not text_value or text_value.lower() in {"nan", "none"}:
        return None
    return text_value


def _row_payload_from_values(values: list[object] | tuple[object, ...]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for index, value in enumerate(values, start=1):
        text_value = _coerce_text(value)
        if text_value is not None:
            payload[f"C{index}"] = text_value
    return payload


def _build_output_row(
    report_month: date,
    period_label: str,
    source_url: str,
    source_file_type: str,
    section_name: str,
    table_index: int,
    row_index: int,
    row_payload: dict[str, str],
) -> dict[str, object] | None:
    if not row_payload:
        return None
    row_text = " | ".join(row_payload.values())
    return {
        "REPORT_MONTH": report_month,
        "PERIOD_LABEL": period_label,
        "SOURCE_URL": source_url,
        "SOURCE_FILE_TYPE": source_file_type,
        "SECTION_NAME": section_name,
        "TABLE_INDEX": int(table_index),
        "ROW_INDEX": int(row_index),
        "ROW_JSON": json.dumps(row_payload, ensure_ascii=False),
        "ROW_TEXT": row_text,
    }


def _parse_excel_report(
    report_content: bytes,
    report_month: date,
    period_label: str,
    source_url: str,
    source_file_type: str,
) -> pd.DataFrame:
    engine = "xlrd" if source_file_type == "xls" else None
    sheets = pd.read_excel(
        io.BytesIO(report_content),
        sheet_name=None,
        header=None,
        dtype=object,
        engine=engine,
    )
    rows: list[dict[str, object]] = []
    for sheet_name, sheet_frame in sheets.items():
        if sheet_frame.empty:
            continue
        for row_index, row_values in enumerate(sheet_frame.itertuples(index=False, name=None), start=1):
            payload = _row_payload_from_values(row_values)
            output_row = _build_output_row(
                report_month=report_month,
                period_label=period_label,
                source_url=source_url,
                source_file_type=source_file_type,
                section_name=f"Sheet:{sheet_name}",
                table_index=1,
                row_index=row_index,
                row_payload=payload,
            )
            if output_row is not None:
                rows.append(output_row)
    if not rows:
        return _empty_output_frame()
    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


def _parse_html_report(
    report_content: bytes,
    report_month: date,
    period_label: str,
    source_url: str,
    source_file_type: str,
) -> pd.DataFrame:
    html_text = report_content.decode("utf-8", errors="ignore")
    tables = pd.read_html(io.StringIO(html_text), header=None)
    rows: list[dict[str, object]] = []
    for table_index, table in enumerate(tables, start=1):
        if table.empty:
            continue
        for row_index, row_values in enumerate(table.itertuples(index=False, name=None), start=1):
            payload = _row_payload_from_values(row_values)
            output_row = _build_output_row(
                report_month=report_month,
                period_label=period_label,
                source_url=source_url,
                source_file_type=source_file_type,
                section_name=f"Table:{table_index}",
                table_index=table_index,
                row_index=row_index,
                row_payload=payload,
            )
            if output_row is not None:
                rows.append(output_row)
    if not rows:
        return _empty_output_frame()
    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


def _parse_pdf_report_with_pdfplumber(
    report_content: bytes,
    report_month: date,
    period_label: str,
    source_url: str,
    source_file_type: str,
) -> pd.DataFrame:
    import pdfplumber

    rows: list[dict[str, object]] = []
    with pdfplumber.open(io.BytesIO(report_content)) as pdf_file:
        for page_index, page in enumerate(pdf_file.pages, start=1):
            extracted_tables = page.extract_tables() or []
            if extracted_tables:
                for table_index, table in enumerate(extracted_tables, start=1):
                    global_table_index = page_index * 1000 + table_index
                    for row_index, row_values in enumerate(table or [], start=1):
                        payload = _row_payload_from_values(row_values or [])
                        output_row = _build_output_row(
                            report_month=report_month,
                            period_label=period_label,
                            source_url=source_url,
                            source_file_type=source_file_type,
                            section_name=f"Page:{page_index}",
                            table_index=global_table_index,
                            row_index=row_index,
                            row_payload=payload,
                        )
                        if output_row is not None:
                            rows.append(output_row)
                continue

            page_text = page.extract_text() or ""
            for row_index, line in enumerate(page_text.splitlines(), start=1):
                payload = _row_payload_from_values([line])
                output_row = _build_output_row(
                    report_month=report_month,
                    period_label=period_label,
                    source_url=source_url,
                    source_file_type=source_file_type,
                    section_name=f"Page:{page_index}",
                    table_index=page_index * 1000,
                    row_index=row_index,
                    row_payload=payload,
                )
                if output_row is not None:
                    rows.append(output_row)

    if not rows:
        return _empty_output_frame()
    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


def _parse_pdf_report_with_pypdf(
    report_content: bytes,
    report_month: date,
    period_label: str,
    source_url: str,
    source_file_type: str,
) -> pd.DataFrame:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(report_content))
    rows: list[dict[str, object]] = []
    for page_index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        for row_index, line in enumerate(page_text.splitlines(), start=1):
            payload = _row_payload_from_values([line])
            output_row = _build_output_row(
                report_month=report_month,
                period_label=period_label,
                source_url=source_url,
                source_file_type=source_file_type,
                section_name=f"Page:{page_index}",
                table_index=page_index * 1000,
                row_index=row_index,
                row_payload=payload,
            )
            if output_row is not None:
                rows.append(output_row)

    if not rows:
        return _empty_output_frame()
    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


def _parse_pdf_report(
    report_content: bytes,
    report_month: date,
    period_label: str,
    source_url: str,
    source_file_type: str,
) -> pd.DataFrame:
    try:
        return _parse_pdf_report_with_pdfplumber(
            report_content=report_content,
            report_month=report_month,
            period_label=period_label,
            source_url=source_url,
            source_file_type=source_file_type,
        )
    except Exception:  # noqa: BLE001
        try:
            return _parse_pdf_report_with_pypdf(
                report_content=report_content,
                report_month=report_month,
                period_label=period_label,
                source_url=source_url,
                source_file_type=source_file_type,
            )
        except Exception as exc:  # noqa: BLE001
            raise NSEdataNotFound(f"Unable to parse AMFI PDF report: {source_url} :: {exc}")


def _parse_report_content(
    report_content: bytes,
    report_month: date,
    period_label: str,
    source_url: str,
    source_file_type: str,
) -> pd.DataFrame:
    if source_file_type in {"xls", "xlsx"}:
        return _parse_excel_report(
            report_content=report_content,
            report_month=report_month,
            period_label=period_label,
            source_url=source_url,
            source_file_type=source_file_type,
        )
    if source_file_type in {"html", "htm"}:
        return _parse_html_report(
            report_content=report_content,
            report_month=report_month,
            period_label=period_label,
            source_url=source_url,
            source_file_type=source_file_type,
        )
    if source_file_type == "pdf":
        return _parse_pdf_report(
            report_content=report_content,
            report_month=report_month,
            period_label=period_label,
            source_url=source_url,
            source_file_type=source_file_type,
        )
    raise NSEdataNotFound(f"Unsupported AMFI monthly report type: {source_file_type}")


def amfi_monthly_report_links() -> pd.DataFrame:
    """
    List all report links exposed on the AMFI monthly archive page.
    """
    response = _amfi_session().get(AMFI_MONTHLY_PAGE_URL, timeout=60)
    if response.status_code != 200:
        raise NSEdataNotFound(f"Unable to access AMFI monthly archive page (status={response.status_code})")
    records = _extract_link_records(response.text)
    if not records:
        return pd.DataFrame(
            columns=[
                "REPORT_MONTH",
                "PERIOD_LABEL",
                "REPORT_YEAR",
                "REPORT_MONTH_NUM",
                "FILE_TYPE",
                "IS_REVISED",
                "SOURCE_URL",
            ]
        )
    frame = pd.DataFrame(records).drop_duplicates(
        subset=["REPORT_MONTH", "FILE_TYPE", "SOURCE_URL"],
        keep="first",
    )
    frame = frame.sort_values(by=["REPORT_MONTH", "FILE_TYPE", "SOURCE_URL"]).reset_index(drop=True)
    return frame[
        [
            "REPORT_MONTH",
            "PERIOD_LABEL",
            "REPORT_YEAR",
            "REPORT_MONTH_NUM",
            "FILE_TYPE",
            "IS_REVISED",
            "SOURCE_URL",
        ]
    ]


def amfi_monthly_data(
    report_month: str | date,
    file_type_priority: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    """
    Fetch a single month AMFI report and return normalized row-wise records.
    """
    normalized_month = _normalize_report_month(report_month)
    priority = tuple(str(value).strip().lower() for value in (file_type_priority or _DEFAULT_FILE_TYPE_PRIORITY))
    links_frame = amfi_monthly_report_links()
    month_links = links_frame[links_frame["REPORT_MONTH"] == normalized_month].copy()
    if month_links.empty:
        return _empty_output_frame()
    selected_link = _preferred_links(month_links, priority).iloc[0]
    source_url = str(selected_link["SOURCE_URL"]).strip()
    source_file_type = str(selected_link["FILE_TYPE"]).strip().lower()
    period_label = str(selected_link["PERIOD_LABEL"]).strip()
    content = _download_report_content(source_url)
    parsed = _parse_report_content(
        report_content=content,
        report_month=normalized_month,
        period_label=period_label,
        source_url=source_url,
        source_file_type=source_file_type,
    )
    return parsed[_OUTPUT_COLUMNS] if not parsed.empty else _empty_output_frame()


def amfi_monthly_historical_data(
    from_month: str | date | None = None,
    to_month: str | date | None = None,
    file_type_priority: tuple[str, ...] | list[str] | None = None,
    include_all_file_variants: bool = False,
    strict: bool = False,
) -> pd.DataFrame:
    """
    Fetch AMFI monthly reports for a historical month range.
    """
    priority = tuple(str(value).strip().lower() for value in (file_type_priority or _DEFAULT_FILE_TYPE_PRIORITY))
    links_frame = amfi_monthly_report_links()
    if links_frame.empty:
        return _empty_output_frame()

    if from_month is not None:
        from_anchor = _normalize_report_month(from_month)
        links_frame = links_frame[links_frame["REPORT_MONTH"] >= from_anchor].copy()
    if to_month is not None:
        to_anchor = _normalize_report_month(to_month)
        links_frame = links_frame[links_frame["REPORT_MONTH"] <= to_anchor].copy()
    if links_frame.empty:
        return _empty_output_frame()

    if include_all_file_variants:
        selected_links = links_frame.sort_values(by=["REPORT_MONTH", "FILE_TYPE", "SOURCE_URL"]).reset_index(drop=True)
    else:
        selected_links = _preferred_links(links_frame, priority)

    output_frames: list[pd.DataFrame] = []
    for report_month in selected_links["REPORT_MONTH"].drop_duplicates().tolist():
        try:
            month_frame = amfi_monthly_data(report_month=report_month, file_type_priority=priority)
        except Exception:
            if strict:
                raise
            continue
        if month_frame.empty:
            continue
        output_frames.append(month_frame)

    if not output_frames:
        return _empty_output_frame()
    return pd.concat(output_frames, ignore_index=True)[_OUTPUT_COLUMNS]

