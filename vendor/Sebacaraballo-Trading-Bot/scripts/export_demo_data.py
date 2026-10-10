"""
scripts/export_demo_data.py
---------------------------
Export the earnings_intel database into the two demo artifacts, keeping the
dashboard, the seed, and the static snapshot on one source of truth:

  1. scripts/demo_data.json
     Raw rows (companies, earnings_dates, filings sans raw_html, signals,
     ALL backtest runs) consumed by scripts/seed_demo.py wherever the
     backend boots with an empty database. In CI this file is also the
     persistent state between daily runs: the workflow restores a DB from
     it, ingests/scores/backtests, and re-exports.

  2. dashboard/public/snapshot/*.json
     Byte-for-byte API responses captured through FastAPI's TestClient,
     shipped with the Vercel build. This is the dashboard's primary data
     source when no live API is configured, and its fallback otherwise:
       stats.json          GET /api/stats
       signals.json        GET /api/signals?limit=500
       filings.json        GET /api/filings?limit=500
       backtest.json       GET /api/backtest/latest
       backtest-runs.json  GET /api/backtest/runs   (full run history)
       filing-texts.json   {filing_id: GET /api/filings/{id}/text}
       meta.json           generation timestamp + counts

Writes are conditional: a file is only rewritten when its content (ignoring
the exported_at / generated_at stamps) actually changed, so a no-new-data CI
run leaves the working tree clean and no commit or redeploy happens. Two
stability rules make that hold in practice:

  * earnings_dates values are treated as volatile for the change decision:
    yfinance revises analyst estimates a little every day, nothing in the
    dashboard displays those values, and without this rule every CI run
    would commit. Fresh earnings data still lands whenever a real change
    (filings/signals/backtest) writes the file.
  * The snapshot is captured from a scratch DB seeded from the just-built
    export, not from the working DB. Row ids in API responses depend on
    insertion order, and a mid-cycle ingest would otherwise renumber them
    on the next restore, rewriting snapshot files with identical content.
    Seeding first makes the snapshot a pure function of demo_data.json.

Run after any change to the dataset (new signals, new backtest run):
    python scripts/export_demo_data.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

DB_PATH = os.getenv("DB_PATH", "earnings_intel.db")
DEMO_DATA_PATH = _PROJECT_ROOT / "scripts" / "demo_data.json"
SNAPSHOT_DIR = _PROJECT_ROOT / "dashboard" / "public" / "snapshot"

# Fields that change on every export and must not count as "data changed".
_VOLATILE_KEYS = {"exported_at", "generated_at"}


def _load_existing(path: Path) -> Optional[object]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _strip_volatile(payload: object, extra_keys: frozenset = frozenset()) -> object:
    if isinstance(payload, dict):
        skip = _VOLATILE_KEYS | extra_keys
        return {k: v for k, v in payload.items() if k not in skip}
    return payload


def _write_if_changed(
    path: Path,
    payload: object,
    ignore_keys: frozenset = frozenset(),
) -> bool:
    """
    Write *payload* as compact JSON only if it differs from what is on disk,
    comparing without the volatile timestamp fields (plus any *ignore_keys*).
    Returns True if written.
    """
    existing = _load_existing(path)
    if existing is not None and (
        _strip_volatile(existing, ignore_keys) == _strip_volatile(payload, ignore_keys)
    ):
        print(f"[export] {path.relative_to(_PROJECT_ROOT)} unchanged")
        return False
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"[export] wrote {path.relative_to(_PROJECT_ROOT)} ({path.stat().st_size:,} bytes)")
    return True


def export_seed_data() -> tuple[dict, bool]:
    """Dump raw DB rows into scripts/demo_data.json. Returns (payload, changed)."""
    from storage.database import Database
    from backtest.store import get_all_backtests

    db = Database(DB_PATH)
    conn = db._conn

    companies = [
        dict(r)
        for r in conn.execute(
            "SELECT ticker, cik, name, exchange, sector FROM companies ORDER BY ticker"
        )
    ]

    earnings_dates = [
        dict(r)
        for r in conn.execute(
            """
            SELECT c.ticker, e.earnings_date, e.eps_estimate, e.eps_actual,
                   e.surprise_pct, e.revenue_estimate, e.revenue_actual
            FROM   earnings_dates e JOIN companies c ON c.id = e.company_id
            ORDER BY c.ticker, e.earnings_date
            """
        )
    ]

    # raw_html is ~4 MB across the DB and nothing downstream reads it — skip it.
    # skip_reason must round-trip so the CI restore cycle keeps prefilter marks.
    filings = [
        dict(r)
        for r in conn.execute(
            """
            SELECT c.ticker, f.accession_number, f.filing_date, f.form_type,
                   f.period_of_report, f.primary_document, f.document_url,
                   f.cleaned_text, f.word_count, f.fetch_status, f.error_message,
                   f.skip_reason
            FROM   filings f JOIN companies c ON c.id = f.company_id
            ORDER BY f.filing_date, f.accession_number
            """
        )
    ]

    signals = []
    for r in conn.execute(
        """
        SELECT c.ticker, f.accession_number, s.signal_date, s.direction,
               s.confidence, s.reasoning, s.key_metrics, s.llm_model,
               s.llm_prompt_tokens, s.llm_completion_tokens,
               s.raw_llm_response, s.created_at
        FROM   signals s
        JOIN   filings f ON f.id = s.filing_id
        JOIN   companies c ON c.id = s.company_id
        ORDER BY s.signal_date, c.ticker, s.created_at
        """
    ):
        row = dict(r)
        # Store the blob as parsed JSON so the file stays readable/diffable.
        row["key_metrics"] = json.loads(row["key_metrics"]) if row["key_metrics"] else None
        signals.append(row)

    # Full run history, oldest first: the record of the strategy evolving.
    backtest_runs = get_all_backtests(db)
    for run in backtest_runs:
        run.pop("id", None)  # row ids are DB-local; the seeder inserts fresh

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "companies": companies,
        "earnings_dates": earnings_dates,
        "filings": filings,
        "signals": signals,
        "backtest_runs": backtest_runs,
    }
    # earnings_dates is volatile (daily yfinance estimate revisions) and feeds
    # nothing user-visible; it must not be able to trigger a commit by itself.
    changed = _write_if_changed(
        DEMO_DATA_PATH, payload, ignore_keys=frozenset({"earnings_dates"})
    )
    return payload, changed


def export_snapshot(payload: dict) -> bool:
    """
    Capture real API responses into dashboard/public/snapshot/. Returns changed.

    Runs against a scratch DB seeded from *payload* (not the working DB), so
    row ids in the captured responses are always the deterministic seed-order
    ids that any future restore of demo_data.json would reproduce.
    """
    norm_db = _PROJECT_ROOT / ".snapshot_norm.db"
    for sidecar in ("", "-wal", "-shm"):
        try:
            Path(f"{norm_db}{sidecar}").unlink()
        except (FileNotFoundError, PermissionError):
            pass

    from storage.database import Database
    from scripts.seed_demo import seed as _seed, seed_backtest as _seed_backtest

    norm = Database(str(norm_db))
    _seed(norm, payload)
    _seed_backtest(norm, payload)

    # api.main reads DB_PATH at import time; point it at the scratch DB. The
    # file is gitignored (*.db) and cleaned up on the next export run, since
    # the API's open connection can keep it locked on Windows until exit.
    os.environ["DB_PATH"] = str(norm_db)
    from fastapi.testclient import TestClient

    from api.main import app

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    client = TestClient(app)

    def get(path: str) -> object:
        res = client.get(path)
        res.raise_for_status()
        return res.json()

    stats = get("/api/stats")
    signals = get("/api/signals?limit=500")
    filings = get("/api/filings?limit=500")
    backtest = get("/api/backtest/latest")
    backtest_runs = get("/api/backtest/runs")

    filing_texts = {}
    for filing in filings:
        if filing["fetch_status"] != "success":
            continue
        res = client.get(f"/api/filings/{filing['id']}/text")
        if res.status_code == 200:
            filing_texts[str(filing["id"])] = res.json()

    changed = False
    changed |= _write_if_changed(SNAPSHOT_DIR / "stats.json", stats)
    changed |= _write_if_changed(SNAPSHOT_DIR / "signals.json", signals)
    changed |= _write_if_changed(SNAPSHOT_DIR / "filings.json", filings)
    changed |= _write_if_changed(SNAPSHOT_DIR / "backtest.json", backtest)
    changed |= _write_if_changed(SNAPSHOT_DIR / "backtest-runs.json", backtest_runs)
    changed |= _write_if_changed(SNAPSHOT_DIR / "filing-texts.json", filing_texts)

    if changed:
        _write_if_changed(
            SNAPSHOT_DIR / "meta.json",
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "signals": len(signals),
                "filings": len(filings),
                "trades": backtest.get("trades_executed") if isinstance(backtest, dict) else None,
                "backtest_runs": len(backtest_runs),
            },
        )
    else:
        print("[export] snapshot unchanged, meta.json kept")
    return changed


def main() -> None:
    payload, seed_changed = export_seed_data()
    snapshot_changed = export_snapshot(payload)
    runs = payload["backtest_runs"]
    latest_trades = runs[-1].get("trades_executed", 0) if runs else 0
    print(
        f"[export] done - {len(payload['signals'])} signals, "
        f"{len(payload['companies'])} companies, {len(payload['filings'])} filings, "
        f"{len(runs)} backtest runs (latest: {latest_trades} trades), "
        f"changed={'yes' if (seed_changed or snapshot_changed) else 'no'}"
    )


if __name__ == "__main__":
    main()
