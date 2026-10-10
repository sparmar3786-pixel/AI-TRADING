"""
scripts/update_readme_results.py
--------------------------------
Regenerate the README Results section from scripts/demo_data.json, so the
README can never disagree with the dashboard or the seeded dataset.

The section lives between these markers in README.md:

    <!-- results:start -->
    ...generated, do not edit by hand...
    <!-- results:end -->

Deterministic: same demo_data.json in, same text out. The daily CI workflow
runs this after the export; if nothing changed, the README is untouched and
no commit happens. Style rules for the generated copy: plain hyphens only
(no em dashes) and no claim that the strategy beats the market.

Run standalone:
    python scripts/update_readme_results.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_DATA_PATH = _PROJECT_ROOT / "scripts" / "demo_data.json"
README_PATH = _PROJECT_ROOT / "README.md"

START_MARKER = "<!-- results:start -->"
END_MARKER = "<!-- results:end -->"

FRAMING_LINE = (
    "Naive equal-weight sizing produces the drawdown shown. Current work:\n"
    "transaction-cost modeling and Kelly-criterion position sizing."
)


def _pct(value: float, signed: bool = True) -> str:
    text = f"{value * 100:.1f}%"
    if signed and value >= 0:
        return f"+{text}"
    return text


def build_results_section(data: dict) -> str:
    runs = data.get("backtest_runs") or []
    if not runs:
        return "No backtest runs recorded yet. Run `python main.py --backtest`."

    latest = runs[-1]
    trades = latest.get("trades", [])
    ticker_count = len({t["ticker"] for t in trades})
    start_year = (latest.get("start_date") or "")[:4]
    end_year = (latest.get("run_date") or "")[:4]
    threshold = latest.get("confidence_threshold")
    first_run_date = (runs[0].get("run_date") or "")[:10]
    latest_run_date = (latest.get("run_date") or "")[:10]

    lines = [
        (
            f"Backtested on {latest.get('trades_executed', 0)} trades across "
            f"{ticker_count} tickers ({start_year}-{end_year}), buying bullish "
            f"signals with confidence >= {threshold} at the filing-date close "
            f"and selling 5 trading days later:"
        ),
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Trades | {latest.get('trades_executed', 0)} |",
        f"| Win Rate | {_pct(latest.get('win_rate', 0.0), signed=False)} |",
        f"| Avg Return per Trade | {_pct(latest.get('avg_return_pct', 0.0))} |",
        f"| Total Return | {_pct(latest.get('total_return_pct', 0.0))} |",
        f"| SPY Benchmark (same period) | {_pct(latest.get('spy_return_pct', 0.0))} |",
        f"| Sharpe Ratio | {latest.get('sharpe_ratio', 0.0):.2f} |",
        f"| Max Drawdown | {_pct(latest.get('max_drawdown_pct', 0.0))} |",
        "",
        FRAMING_LINE,
        "",
        (
            f"Latest run: {latest_run_date}. Run history: {len(runs)} backtests "
            f"recorded since {first_run_date}, refreshed automatically by the "
            f"daily data pipeline."
        ),
    ]
    return "\n".join(lines)


def main() -> None:
    data = json.loads(DEMO_DATA_PATH.read_text(encoding="utf-8"))
    readme = README_PATH.read_text(encoding="utf-8")

    start = readme.find(START_MARKER)
    end = readme.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        print(
            "[readme] markers not found; README.md must contain "
            f"{START_MARKER} and {END_MARKER}",
            file=sys.stderr,
        )
        sys.exit(1)

    section = build_results_section(data)
    updated = (
        readme[: start + len(START_MARKER)]
        + "\n"
        + section
        + "\n"
        + readme[end:]
    )

    if updated == readme:
        print("[readme] Results section unchanged")
        return

    README_PATH.write_text(updated, encoding="utf-8")
    print("[readme] Results section regenerated")


if __name__ == "__main__":
    main()
