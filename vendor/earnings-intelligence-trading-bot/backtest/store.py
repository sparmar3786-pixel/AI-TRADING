"""
backtest/store.py
-----------------
Persistence for Phase 3 backtest runs.

The ``backtest_runs`` table is defined in storage/database.py; Phase 3 result
columns (trades_json, equity_curve_json, win_rate, …) are added by
``Database._migrate_backtest_columns`` so this module can assume they exist.

Convention: every ratio/return field is a DECIMAL FRACTION (0.05 == 5%),
matching the engine.  The CLI and dashboard multiply by 100 for display.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from storage.database import Database


def save_backtest_run(db: Database, results: dict[str, Any]) -> int:
    """
    Persist a backtest results dict to ``backtest_runs``.

    Trades and the equity curve are stored as JSON blobs; scalar metrics map to
    individual columns so summaries can be queried without parsing JSON.

    Args:
        db:      Open Database instance.
        results: The dict returned by ``BacktestEngine.run()``.

    Returns:
        The new ``backtest_runs.id``.
    """
    trades = results.get("trades", [])
    tickers = sorted({t["ticker"] for t in trades})

    with db._cursor() as cur:
        cur.execute(
            """
            INSERT INTO backtest_runs (
                run_name, start_date, end_date, tickers, strategy_config,
                total_trades, winning_trades, total_pnl, sharpe_ratio, max_drawdown,
                run_date, confidence_threshold, total_signals_evaluated,
                trades_skipped, win_rate, avg_return_pct, total_return_pct,
                spy_return_pct, trades_json, equity_curve_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"backtest {results.get('run_date', '')}",
                results.get("start_date"),
                results.get("run_date", "")[:10] or None,
                json.dumps(tickers),
                json.dumps({"confidence_threshold": results.get("confidence_threshold")}),
                results.get("trades_executed", 0),
                sum(1 for t in trades if t.get("return_pct", 0) > 0),
                results.get("total_return_pct", 0.0),
                results.get("sharpe_ratio", 0.0),
                results.get("max_drawdown_pct", 0.0),
                results.get("run_date"),
                results.get("confidence_threshold"),
                results.get("total_signals_evaluated", 0),
                results.get("trades_skipped", 0),
                results.get("win_rate", 0.0),
                results.get("avg_return_pct", 0.0),
                results.get("total_return_pct", 0.0),
                results.get("spy_return_pct", 0.0),
                json.dumps(trades),
                json.dumps(results.get("equity_curve", [])),
            ),
        )
        return int(cur.lastrowid)  # type: ignore[arg-type]


def _row_to_results(r: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the ``BacktestEngine.run()`` results shape from a table row."""
    return {
        "id": r["id"],
        "run_date": r.get("run_date"),
        "start_date": r.get("start_date"),
        "confidence_threshold": r.get("confidence_threshold"),
        "total_signals_evaluated": r.get("total_signals_evaluated"),
        "trades_executed": r.get("total_trades"),
        "trades_skipped": r.get("trades_skipped"),
        "win_rate": r.get("win_rate"),
        "avg_return_pct": r.get("avg_return_pct"),
        "total_return_pct": r.get("total_return_pct"),
        "sharpe_ratio": r.get("sharpe_ratio"),
        "max_drawdown_pct": r.get("max_drawdown"),
        "spy_return_pct": r.get("spy_return_pct"),
        "trades": json.loads(r.get("trades_json") or "[]"),
        "equity_curve": json.loads(r.get("equity_curve_json") or "[]"),
    }


def get_all_backtests(db: Database) -> list[dict[str, Any]]:
    """
    Return every backtest run as a full results dict, oldest first.

    The run history is the record of the strategy evolving over time, so the
    demo export keeps all of it (see scripts/export_demo_data.py).
    """
    rows = db._conn.execute(
        "SELECT * FROM backtest_runs ORDER BY id ASC"
    ).fetchall()
    return [_row_to_results(dict(r)) for r in rows]


def get_latest_backtest(db: Database) -> Optional[dict[str, Any]]:
    """
    Return the most recent backtest run as a full results dict, or None.

    Re-hydrates trades_json / equity_curve_json into Python objects and rebuilds
    the same shape ``BacktestEngine.run()`` produced.
    """
    row = db._conn.execute(
        "SELECT * FROM backtest_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return _row_to_results(dict(row))


def list_backtest_runs(db: Database) -> list[dict[str, Any]]:
    """
    Return lightweight summaries of every backtest run (newest first).

    Excludes the trades/equity_curve blobs — used by ``/api/backtest/runs``.
    """
    rows = db._conn.execute(
        """
        SELECT id, run_date, total_trades, win_rate, sharpe_ratio, total_return_pct
        FROM   backtest_runs
        ORDER BY id DESC
        """
    ).fetchall()
    return [
        {
            "id": r["id"],
            "run_date": r["run_date"],
            "trades_executed": r["total_trades"],
            "win_rate": r["win_rate"],
            "sharpe_ratio": r["sharpe_ratio"],
            "total_return_pct": r["total_return_pct"],
        }
        for r in rows
    ]
