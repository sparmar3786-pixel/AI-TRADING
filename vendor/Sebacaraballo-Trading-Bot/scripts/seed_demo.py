"""
scripts/seed_demo.py
--------------------
Seed an empty database with the full demo dataset exported from the real
pipeline (scripts/demo_data.json, produced by scripts/export_demo_data.py):
LLM-scored signals across 10 tickers, their filings and earnings dates, and
the complete backtest run history. The daily CI workflow also uses this as
its state restore: fresh runner, seed from the committed export, then ingest
and score only what is new.

Behaviour:
  * Idempotent — if the ``signals`` table already has any rows, the dataset
    seed is skipped (safe to run on every backend boot). The backtest seed has
    its own independent check on ``backtest_runs``.
  * Creates the schema if the DB file doesn't exist yet (a fresh container
    starts with no DB, since *.db is gitignored).
  * Inserts ``companies`` and ``filings`` rows first and maps their fresh ids
    so the signal foreign keys resolve.
  * Backtest runs are inserted verbatim from the export (oldest first, all of
    them) — no yfinance calls at boot, so results always match the static
    snapshot and the README, and the run history survives restore cycles.

Run standalone:
    python scripts/seed_demo.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow `python scripts/seed_demo.py` from anywhere by putting the project
# root (the parent of scripts/) on the import path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from storage.database import Database  # noqa: E402  (import after sys.path tweak)
from backtest.store import save_backtest_run  # noqa: E402

# Same env var / default the API uses, so both read & write the same file.
DB_PATH = os.getenv("DB_PATH", "earnings_intel.db")

DEMO_DATA_PATH = _PROJECT_ROOT / "scripts" / "demo_data.json"


def _load_demo_data() -> dict:
    with DEMO_DATA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def seed(db: Database, data: dict) -> int:
    """Insert the exported dataset. Returns the number of signals inserted."""
    company_ids: dict[str, int] = {}
    for company in data["companies"]:
        company_ids[company["ticker"]] = db.upsert_company(
            ticker=company["ticker"],
            cik=company["cik"],
            name=company["name"],
            exchange=company["exchange"],
            sector=company["sector"],
        )
    print(f"[seed] upserted {len(company_ids)} companies")

    for ed in data["earnings_dates"]:
        db.upsert_earnings_date(
            company_id=company_ids[ed["ticker"]],
            # upsert_earnings_date calls .isoformat(); the export stores the
            # isoformat string, so this round-trips to the exact stored value.
            earnings_date=datetime.fromisoformat(ed["earnings_date"]),
            eps_estimate=ed["eps_estimate"],
            eps_actual=ed["eps_actual"],
            surprise_pct=ed["surprise_pct"],
            revenue_estimate=ed["revenue_estimate"],
            revenue_actual=ed["revenue_actual"],
        )
    print(f"[seed] upserted {len(data['earnings_dates'])} earnings dates")

    filing_ids: dict[str, int] = {}
    for filing in data["filings"]:
        filing_id = db.upsert_filing(
            company_id=company_ids[filing["ticker"]],
            accession_number=filing["accession_number"],
            filing_date=filing["filing_date"],
            form_type=filing["form_type"],
            period_of_report=filing["period_of_report"],
            primary_document=filing["primary_document"],
            document_url=filing["document_url"],
            cleaned_text=filing["cleaned_text"],
            word_count=filing["word_count"],
            fetch_status=filing["fetch_status"],
            error_message=filing["error_message"],
        )
        filing_ids[filing["accession_number"]] = filing_id
        # Restore the analysis prefilter mark so CI runs don't re-check
        # filings already known to carry no earnings exhibit.
        if filing.get("skip_reason"):
            db.set_filing_skip_reason(filing_id, filing["skip_reason"])
    print(f"[seed] upserted {len(filing_ids)} filings")

    inserted = 0
    for signal in data["signals"]:
        key_metrics = (
            json.dumps(signal["key_metrics"], ensure_ascii=False)
            if signal["key_metrics"] is not None
            else None
        )
        db._conn.execute(
            """
            INSERT INTO signals
                (filing_id, company_id, signal_date, direction, confidence,
                 reasoning, key_metrics, llm_model,
                 llm_prompt_tokens, llm_completion_tokens, raw_llm_response,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filing_ids[signal["accession_number"]],
                company_ids[signal["ticker"]],
                signal["signal_date"],
                signal["direction"],
                signal["confidence"],
                signal["reasoning"],
                key_metrics,
                signal["llm_model"],
                signal["llm_prompt_tokens"],
                signal["llm_completion_tokens"],
                signal["raw_llm_response"],
                signal["created_at"],
            ),
        )
        inserted += 1
    db._conn.commit()
    print(f"[seed] inserted {inserted} signals")

    return inserted


def seed_backtest(db: Database, data: dict) -> None:
    """
    Insert the complete exported backtest run history (oldest first) so the
    dashboard shows the same numbers as the static snapshot and the README,
    and the record of the strategy evolving over time is preserved.

    Has its own idempotency check (independent of the signals seed) so it still
    runs on a reboot where signals already exist. Wrapped in try/except: a bad
    or missing export must never block startup — the signals still serve.
    """
    existing = db._conn.execute("SELECT COUNT(*) AS n FROM backtest_runs").fetchone()["n"]
    if existing > 0:
        print("[seed] Backtest runs already exist, skipping")
        return

    runs = data.get("backtest_runs") or []
    if not runs:
        print("[seed] No backtest runs in demo_data.json, skipping")
        return

    try:
        for results in runs:
            save_backtest_run(db, results)
        latest = runs[-1]
        print(
            f"[seed] Backtest history seeded ({len(runs)} runs, "
            f"latest: {latest.get('trades_executed', 0)} trades)"
        )
    except Exception as exc:
        print(f"[seed] Backtest seeding failed (skipping): {exc}")


def main() -> None:
    db = Database(DB_PATH)
    data = _load_demo_data()

    existing = db._conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"]
    if existing > 0:
        print(
            f"[seed] signals table already has {existing} row(s) — "
            "skipping demo seed (idempotent)."
        )
    else:
        count = seed(db, data)
        print(f"[seed] done — inserted {count} demo signals into {db.db_path}")

    seed_backtest(db, data)


if __name__ == "__main__":
    main()
