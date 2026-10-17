"""Exchange holiday calendar with an official-source snapshot and safe refresh.

The checked-in 2026 dates are a last-known-good fallback, not a claim that every
exchange/segment calendar is covered. NSE refresh is best-effort; failed or
unparseable source responses never erase the last-known-good data.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

NSE_SOURCE_URL = "https://www.nseindia.com/resources/exchange-communication-holidays?apiversion=v2"
SOURCE_AS_OF = "2026-10-17"
_TIMEZONE = "Asia/Kolkata"
_LOCK = threading.RLock()
_REFRESH_THREAD: threading.Thread | None = None

# Official NSE 2026 equity holiday list as published at SOURCE_AS_OF.
# BSE shares the listed exchange-wide dates below; the NSE-only Maharashtra
# municipal election holiday is deliberately not copied to BSE.
_COMMON_2026 = [
    ("2026-01-26", "Republic Day"),
    ("2026-03-03", "Holi"),
    ("2026-03-26", "Shri Ram Navami"),
    ("2026-03-31", "Shri Mahavir Jayanti"),
    ("2026-04-03", "Good Friday"),
    ("2026-04-14", "Dr. B. R. Ambedkar Jayanti"),
    ("2026-05-01", "Maharashtra Day"),
    ("2026-05-28", "Bakri Id"),
    ("2026-06-26", "Muharram"),
    ("2026-09-14", "Ganesh Chaturthi"),
    ("2026-10-02", "Mahatma Gandhi Jayanti"),
    ("2026-10-20", "Dussehra"),
    ("2026-11-10", "Diwali-Balipratipada"),
    ("2026-11-24", "Prakash Gurpurb Sri Guru Nanak Dev"),
    ("2026-12-25", "Christmas"),
]
_NSE_ONLY_2026 = [("2026-01-15", "Municipal Corporation Election - Maharashtra")]
_SPECIAL_2026 = [{
    "date": "2026-11-08",
    "name": "Diwali Laxmi Pujan / Muhurat Trading",
    "kind": "SPECIAL_SESSION",
    "regular_session": False,
    "timing_status": "PENDING_OFFICIAL_TIMINGS",
    "source_url": NSE_SOURCE_URL,
}]
_SEGMENTS = {"NSE_EQ", "NSE_FO", "BSE_EQ", "BSE_FO", "MCX"}
_DATA: dict[str, Any] = {
    "NSE_EQ": {"holidays": _rows(_COMMON_2026 + _NSE_ONLY_2026), "source_status": "CHECKED_IN_OFFICIAL_SNAPSHOT"},
    "NSE_FO": {"holidays": _rows(_COMMON_2026 + _NSE_ONLY_2026), "source_status": "CHECKED_IN_OFFICIAL_SNAPSHOT"},
    "BSE_EQ": {"holidays": _rows(_COMMON_2026), "source_status": "CHECKED_IN_COMMON_EXCHANGE_SNAPSHOT"},
    "BSE_FO": {"holidays": _rows(_COMMON_2026), "source_status": "CHECKED_IN_COMMON_EXCHANGE_SNAPSHOT"},
    "MCX": {"holidays": [], "source_status": "UNVERIFIED_NO_OFFICIAL_SNAPSHOT"},
}
for _segment in ("NSE_EQ", "NSE_FO", "BSE_EQ", "BSE_FO"):
    _DATA[_segment]["special_sessions"] = [dict(item) for item in _SPECIAL_2026] if _segment.startswith(("NSE", "BSE")) else []


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join(part for part in self._cell if part).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _calendar_path() -> Path:
    return Path(os.getenv("EXCHANGE_CALENDAR_FILE", "/data/exchange_holidays.json"))


def _read_persisted() -> dict[str, Any] | None:
    try:
        raw = json.loads(_calendar_path().read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) and isinstance(raw.get("segments"), dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _write_persisted() -> bool:
    path = _calendar_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"source_url": NSE_SOURCE_URL, "updated_at": datetime.now(timezone.utc).isoformat(), "segments": _DATA}, separators=(",", ":"))
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
        return True
    except OSError:
        return False


def _load_persisted_once() -> None:
    persisted = _read_persisted()
    if not persisted:
        return
    with _LOCK:
        segments = persisted.get("segments") or {}
        for segment in _SEGMENTS:
            existing = segments.get(segment)
            if isinstance(existing, dict) and isinstance(existing.get("holidays"), list):
                _DATA[segment] = existing


_load_persisted_once()


def _parse_date_cell(text: str) -> str | None:
    for pattern, fmt in (
        (r"\b(\d{1,2}-[A-Za-z]{3}-\d{4})\b", "%d-%b-%Y"),
        (r"\b(\d{1,2}-[A-Za-z]{3}-\d{2})\b", "%d-%b-%y"),
        (r"\b(\d{4}-\d{2}-\d{2})\b", "%Y-%m-%d"),
    ):
        found = re.search(pattern, text)
        if found:
            try:
                return datetime.strptime(found.group(1), fmt).date().isoformat()
            except ValueError:
                pass
    return None


def refresh_nse_calendar(timeout_seconds: float = 8.0) -> dict[str, Any]:
    """Best-effort refresh. A malformed/blocked source leaves the prior data intact."""
    request = urllib.request.Request(
        NSE_SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AI-TRADING-ExchangeCalendar/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            html = response.read(4_000_000).decode("utf-8", errors="replace")
        parser = _TableParser()
        parser.feed(html)
        year = date.today().year
        parsed: dict[str, str] = {}
        for row in parser.rows:
            joined = " | ".join(row)
            day = next((_parse_date_cell(cell) for cell in row if _parse_date_cell(cell)), None)
            if not day or not day.startswith(f"{year}-"):
                continue
            name = next((cell.strip() for cell in reversed(row) if cell.strip() and _parse_date_cell(cell) is None and not re.fullmatch(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", cell, re.I)), "")
            if name and name.lower() not in {"date", "day", "description", "holiday"}:
                parsed[day] = name[:160]
        if len(parsed) < 6:
            return {"updated": False, "status": "SOURCE_UNPARSEABLE_OR_INCOMPLETE", "parsed_count": len(parsed)}
        rows = [{"date": day, "name": name, "kind": "HOLIDAY"} for day, name in sorted(parsed.items())]
        with _LOCK:
            for segment in ("NSE_EQ", "NSE_FO"):
                _DATA[segment] = {
                    **_DATA.get(segment, {}),
                    "holidays": rows,
                    "source_status": "LIVE_REFRESHED_OFFICIAL_NSE",
                    "source_url": NSE_SOURCE_URL,
                    "source_updated_at": datetime.now(timezone.utc).isoformat(),
                }
            persisted = _write_persisted()
        return {"updated": True, "status": "LIVE_REFRESHED_OFFICIAL_NSE", "parsed_count": len(rows), "persisted": persisted}
    except Exception as exc:
        return {"updated": False, "status": "LAST_KNOWN_GOOD_RETAINED", "error_type": type(exc).__name__}


def _refresh_loop() -> None:
    while True:
        refresh_nse_calendar()
        time.sleep(24 * 60 * 60)


def start_refresh_scheduler() -> None:
    global _REFRESH_THREAD
    with _LOCK:
        if _REFRESH_THREAD is not None and _REFRESH_THREAD.is_alive():
            return
        _REFRESH_THREAD = threading.Thread(target=_refresh_loop, name="exchange-calendar-refresh", daemon=True)
        _REFRESH_THREAD.start()


def holidays_for(segment: str, year: int) -> dict[str, Any]:
    key = segment.strip().upper()
    if key not in _SEGMENTS:
        key = "NSE_FO"
    with _LOCK:
        entry = dict(_DATA[key])
    holiday_rows = [dict(item) for item in entry.get("holidays", []) if str(item.get("date", "")).startswith(f"{year}-")]
    special_rows = [dict(item) for item in entry.get("special_sessions", []) if str(item.get("date", "")).startswith(f"{year}-")]
    covered = entry.get("source_status") != "UNVERIFIED_NO_OFFICIAL_SNAPSHOT"
    return {
        "segment": key,
        "year": year,
        "timezone": _TIMEZONE,
        "source_url": entry.get("source_url", NSE_SOURCE_URL if key.startswith("NSE") else None),
        "source_as_of": entry.get("source_updated_at", SOURCE_AS_OF if year == 2026 else None),
        "source_status": entry.get("source_status", "UNVERIFIED_NO_OFFICIAL_SNAPSHOT") if year == 2026 else ("LIVE_REFRESHED_OFFICIAL_NSE" if entry.get("source_updated_at") else "UNVERIFIED_NO_OFFICIAL_SNAPSHOT"),
        "verified": bool(covered and (year == 2026 or entry.get("source_updated_at"))),
        "holidays": holiday_rows,
        "special_sessions": special_rows,
        "note": "Dates are a last-known-good official-source snapshot. MCX has no verified calendar in this module; never infer MCX holidays from NSE/BSE.",
    }


def day_status(day: date, segment: str) -> dict[str, Any]:
    calendar = holidays_for(segment, day.year)
    holiday = next((item for item in calendar["holidays"] if item["date"] == day.isoformat()), None)
    special = next((item for item in calendar["special_sessions"] if item["date"] == day.isoformat()), None)
    weekend = day.weekday() >= 5
    if special:
        status = "SPECIAL_SESSION"
    elif holiday:
        status = "EXCHANGE_HOLIDAY"
    elif weekend:
        status = "WEEKEND"
    elif not calendar["verified"]:
        status = "CALENDAR_UNVERIFIED"
    else:
        status = "REGULAR_SESSION_DAY"
    return {
        "date": day.isoformat(),
        "segment": calendar["segment"],
        "is_holiday": holiday is not None or (special is not None and not special.get("regular_session", False)),
        "is_weekend": weekend,
        "market_status": status,
        "holiday_name": holiday.get("name") if holiday else (special.get("name") if special else None),
        "special_session": special,
        "calendar_verified": calendar["verified"],
        "source_status": calendar["source_status"],
    }


def segment_for_symbol(symbol: str) -> str:
    key = symbol.strip().upper()
    if key in {"SENSEX", "BANKEX"}:
        return "BSE_FO"
    if key in {"CRUDEOIL", "CRUDEOILM", "NATURALGAS", "NATGASMINI", "GOLD", "GOLDM", "SILVER", "SILVERM", "COPPER", "ZINC", "ALUMINIUM", "LEAD", "NICKEL", "MENTHAOIL", "CASTORSEED", "COTTON", "RUBBER"}:
        return "MCX"
    return "NSE_FO"
