"""
backtest/engine.py
------------------
Phase 3 backtesting engine.

Replays every qualifying LLM signal against real historical prices and measures
whether the "buy bullish earnings" strategy actually worked:

  signal (bullish, high-confidence)
    → buy at the close on the filing date (or next trading day)
    → sell 5 trading days later
    → measure return, then aggregate into win rate / Sharpe / drawdown
    → compare against SPY over the same window

The trade simulation, Sharpe, and max-drawdown are implemented manually with
numpy (no vectorbt) — clearer to read and to explain in an interview.

Return-value convention
------------------------
Every ratio/return field is a DECIMAL FRACTION (0.05 == 5%):
``win_rate``, ``return_pct``, ``avg_return_pct``, ``total_return_pct``,
``max_drawdown_pct`` (<= 0), ``spy_return_pct``.  ``sharpe_ratio`` is a plain
number.  The CLI and dashboard multiply by 100 for display.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from storage.database import Database

# Strategy constants
_HOLD_DAYS = 5            # trading days held per trade
_START_CAPITAL = 10_000.0  # equity curve starting value (USD)
_TRADING_DAYS_PER_YEAR = 252
_MIN_SIGNALS_WARN = 5     # below this, results aren't statistically meaningful

# yfinance retry policy. Yahoo throttles shared cloud IPs (GitHub Actions
# runners especially), so a single failed download must not sink the run.
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_BACKOFF_SECONDS = 3.0  # 3s, then 6s between attempts


class BacktestEngine:
    """
    Orchestrates a full backtest: load signals → fetch prices → simulate → metrics.

    Args:
        db_path: SQLite path. ``None`` uses the Database default (earnings_intel.db).
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db = Database(db_path) if db_path else Database()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        start_date: str = "2024-01-01",
        confidence_threshold: float = 0.6,
    ) -> dict[str, Any]:
        """
        Run the backtest and return a results dict (see module docstring for the
        fraction convention).  Safe to call with zero signals — returns an empty
        but well-formed result.
        """
        print(
            f"[Backtest] Starting — start_date={start_date}, "
            f"confidence_threshold={confidence_threshold}"
        )

        signals = self._load_signals(start_date, confidence_threshold)

        if len(signals) < _MIN_SIGNALS_WARN:
            print(
                f"[Backtest] Warning: only {len(signals)} signals analyzed. "
                "Run --analyze on more tickers for meaningful results."
            )

        if not signals:
            return self._empty_results(start_date, confidence_threshold)

        prices = self._fetch_prices(signals)
        trades = self._simulate(signals, prices)
        metrics = self._compute_metrics(trades)

        results: dict[str, Any] = {
            "run_date": datetime.now().isoformat(timespec="seconds"),
            "start_date": start_date,
            "confidence_threshold": confidence_threshold,
            "total_signals_evaluated": len(signals),
            "trades_executed": len(trades),
            "trades_skipped": len(signals) - len(trades),
            **metrics,
        }
        print(
            f"[Backtest] Done — {results['trades_executed']} trades, "
            f"win_rate={results['win_rate']:.1%}, "
            f"total_return={results['total_return_pct']:+.2%}, "
            f"sharpe={results['sharpe_ratio']:.2f}"
        )
        return results

    # ------------------------------------------------------------------
    # Step 1 — load signals
    # ------------------------------------------------------------------

    def _load_signals(
        self,
        start_date: str,
        confidence_threshold: float,
    ) -> list[dict[str, Any]]:
        """
        Load bullish, high-confidence signals filed on/after ``start_date``.

        ``sentiment`` lives inside the ``signals.key_metrics`` JSON blob (Phase 2),
        so we extract it with SQLite's ``json_extract`` and fall back to the
        ``direction`` column ('LONG' → bullish) when the blob lacks it.
        """
        rows = self._db._conn.execute(
            """
            SELECT s.id                                          AS signal_id,
                   c.ticker                                      AS ticker,
                   f.filing_date                                 AS filing_date,
                   s.confidence                                  AS confidence,
                   s.direction                                   AS direction,
                   json_extract(s.key_metrics, '$.sentiment')    AS sentiment
            FROM   signals   s
            JOIN   filings   f ON f.id = s.filing_id
            JOIN   companies c ON c.id = s.company_id
            WHERE  f.filing_date >= ?
            ORDER BY f.filing_date ASC
            """,
            (start_date,),
        ).fetchall()

        signals: list[dict[str, Any]] = []
        for row in rows:
            r = dict(row)
            sentiment = r.get("sentiment") or (
                "bullish" if r.get("direction") == "LONG" else "neutral"
            )
            if sentiment != "bullish":
                continue
            if (r.get("confidence") or 0.0) < confidence_threshold:
                continue
            signals.append(
                {
                    "signal_id": r["signal_id"],
                    "ticker": r["ticker"],
                    "filing_date": r["filing_date"],
                    "sentiment": sentiment,
                    "confidence": r["confidence"],
                }
            )

        tickers = sorted({s["ticker"] for s in signals})
        print(
            f"[Backtest] Loaded {len(signals)} qualifying signals "
            f"from {len(tickers)} tickers"
        )
        return signals

    # ------------------------------------------------------------------
    # Step 2 — fetch prices
    # ------------------------------------------------------------------

    def _fetch_prices(self, signals: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
        """
        Download daily prices for every unique ticker via yfinance.

        Returns a dict mapping ticker → DataFrame with a DatetimeIndex and a
        'Close' column.  Tickers that fail or return no data are omitted (the
        simulator then skips their trades).
        """
        tickers = sorted({s["ticker"] for s in signals})
        earliest = min(s["filing_date"] for s in signals)
        # Buffer back a week so the entry trading day is always in range.
        start = (datetime.fromisoformat(earliest) - timedelta(days=7)).date().isoformat()
        end = (date.today() + timedelta(days=1)).isoformat()

        prices: dict[str, pd.DataFrame] = {}
        fetched: list[str] = []
        for ticker in tickers:
            df = self._download_with_retry(ticker, start, end)
            if df is None:
                print(f"[Backtest]   ! no price data returned for {ticker}")
                continue

            prices[ticker] = df
            fetched.append(ticker)

        print(f"[Backtest] Fetched price data for: {', '.join(fetched) or '(none)'}")
        return prices

    def _download_with_retry(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """
        Download and normalize daily prices, retrying transient failures with
        exponential backoff. Returns None once all attempts are exhausted.
        """
        for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
            try:
                df = yf.download(
                    symbol,
                    start=start,
                    end=end,
                    auto_adjust=True,
                    progress=False,
                )
            except Exception as exc:
                df = None
                print(
                    f"[Backtest]   ! price fetch failed for {symbol} "
                    f"(attempt {attempt}/{_DOWNLOAD_ATTEMPTS}): {exc}"
                )
            else:
                df = self._normalize_prices(df)
                if df is not None and not df.empty:
                    return df
                print(
                    f"[Backtest]   ! empty price data for {symbol} "
                    f"(attempt {attempt}/{_DOWNLOAD_ATTEMPTS})"
                )

            if attempt < _DOWNLOAD_ATTEMPTS:
                time.sleep(_DOWNLOAD_BACKOFF_SECONDS * attempt)

        return None

    @staticmethod
    def _normalize_prices(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Flatten yfinance's (possibly MultiIndex) columns to a single 'Close' frame."""
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            # yfinance returns columns like ('Close', 'AAPL'); keep the price level.
            df.columns = df.columns.get_level_values(0)
        if "Close" not in df.columns:
            return None
        out = df[["Close"]].dropna()
        return out if not out.empty else None

    # ------------------------------------------------------------------
    # Step 3 — simulate trades
    # ------------------------------------------------------------------

    def _simulate(
        self,
        signals: list[dict[str, Any]],
        prices: dict[str, pd.DataFrame],
    ) -> list[dict[str, Any]]:
        """
        Convert each signal into a long trade: buy on the filing date (or the next
        trading day), sell ``_HOLD_DAYS`` trading days later.  Signals without
        usable price data are skipped with a logged reason.
        """
        trades: list[dict[str, Any]] = []
        skipped = 0

        for sig in signals:
            ticker = sig["ticker"]
            df = prices.get(ticker)
            if df is None:
                skipped += 1
                print(f"[Backtest]   skip {ticker} {sig['filing_date']}: no price data")
                continue

            close = df["Close"]
            index = close.index
            target = pd.Timestamp(sig["filing_date"])

            # First trading day on/after the filing date.
            entry_pos = int(index.searchsorted(target, side="left"))
            if entry_pos >= len(index):
                skipped += 1
                print(
                    f"[Backtest]   skip {ticker} {sig['filing_date']}: "
                    "filing date beyond available prices"
                )
                continue

            exit_pos = entry_pos + _HOLD_DAYS
            if exit_pos >= len(index):
                skipped += 1
                print(
                    f"[Backtest]   skip {ticker} {sig['filing_date']}: "
                    f"fewer than {_HOLD_DAYS} trading days after entry"
                )
                continue

            entry_price = float(close.iloc[entry_pos])
            exit_price = float(close.iloc[exit_pos])
            if not (entry_price > 0):
                skipped += 1
                print(f"[Backtest]   skip {ticker} {sig['filing_date']}: bad entry price")
                continue

            trades.append(
                {
                    "signal_id": sig["signal_id"],
                    "ticker": ticker,
                    "entry_date": index[entry_pos].strftime("%Y-%m-%d"),
                    "exit_date": index[exit_pos].strftime("%Y-%m-%d"),
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "return_pct": (exit_price - entry_price) / entry_price,
                    "direction": "long",
                }
            )

        print(
            f"[Backtest] Simulated {len(trades)} trades "
            f"({skipped} skipped — no price data)"
        )
        return trades

    # ------------------------------------------------------------------
    # Step 4 — metrics
    # ------------------------------------------------------------------

    def _compute_metrics(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Aggregate trades into win rate, average/total return, Sharpe, max drawdown,
        an equity curve, and a SPY benchmark over the same window.
        """
        if not trades:
            return {
                "win_rate": 0.0,
                "avg_return_pct": 0.0,
                "total_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "spy_return_pct": 0.0,
                "trades": [],
                "equity_curve": [],
            }

        # Chronological order matters for the equity curve and drawdown.
        chrono = sorted(trades, key=lambda t: t["exit_date"])
        returns = np.array([t["return_pct"] for t in chrono], dtype=float)

        win_rate = float(np.mean(returns > 0))
        avg_return = float(np.mean(returns))

        # Equity curve: equal capital, sequentially compounded.
        equity = _START_CAPITAL
        equity_curve = [
            {"date": chrono[0]["entry_date"], "value": round(_START_CAPITAL, 2)}
        ]
        for t in chrono:
            equity *= 1.0 + t["return_pct"]
            equity_curve.append({"date": t["exit_date"], "value": round(equity, 2)})

        total_return = equity / _START_CAPITAL - 1.0

        # Sharpe (annualized for a 5-day holding period). Undefined for <2 trades
        # or zero dispersion → 0.0.
        if len(returns) >= 2:
            std = float(np.std(returns, ddof=1))
            sharpe = (
                (avg_return / std) * math.sqrt(_TRADING_DAYS_PER_YEAR / _HOLD_DAYS)
                if std > 0
                else 0.0
            )
        else:
            sharpe = 0.0

        max_drawdown = self._max_drawdown([p["value"] for p in equity_curve])
        spy_return = self._spy_return(chrono)

        return {
            "win_rate": win_rate,
            "avg_return_pct": avg_return,
            "total_return_pct": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_drawdown,
            "spy_return_pct": spy_return,
            "trades": chrono,
            "equity_curve": equity_curve,
        }

    @staticmethod
    def _max_drawdown(values: list[float]) -> float:
        """Largest peak-to-trough decline of an equity series, as a fraction <= 0."""
        peak = -math.inf
        max_dd = 0.0
        for v in values:
            peak = max(peak, v)
            if peak > 0:
                dd = (v - peak) / peak
                max_dd = min(max_dd, dd)
        return float(max_dd)

    def _spy_return(self, trades: list[dict[str, Any]]) -> float:
        """
        SPY buy-and-hold return from the first entry to the last exit, as a
        fraction.  Returns 0.0 if SPY data can't be fetched.
        """
        first_entry = min(t["entry_date"] for t in trades)
        last_exit = max(t["exit_date"] for t in trades)
        try:
            start = (datetime.fromisoformat(first_entry) - timedelta(days=7)).date().isoformat()
            end = (datetime.fromisoformat(last_exit) + timedelta(days=2)).date().isoformat()
            df = self._download_with_retry("SPY", start, end)
            if df is None or df.empty:
                print("[Backtest]   ! SPY benchmark unavailable")
                return 0.0
            close = df["Close"]
            index = close.index
            i0 = int(index.searchsorted(pd.Timestamp(first_entry), side="left"))
            i1 = int(index.searchsorted(pd.Timestamp(last_exit), side="right")) - 1
            i0 = min(i0, len(index) - 1)
            i1 = min(max(i1, 0), len(index) - 1)
            p0, p1 = float(close.iloc[i0]), float(close.iloc[i1])
            return (p1 - p0) / p0 if p0 > 0 else 0.0
        except Exception as exc:
            print(f"[Backtest]   ! SPY benchmark fetch failed: {exc}")
            return 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_results(start_date: str, confidence_threshold: float) -> dict[str, Any]:
        """Well-formed results dict for the zero-signal case."""
        return {
            "run_date": datetime.now().isoformat(timespec="seconds"),
            "start_date": start_date,
            "confidence_threshold": confidence_threshold,
            "total_signals_evaluated": 0,
            "trades_executed": 0,
            "trades_skipped": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "spy_return_pct": 0.0,
            "trades": [],
            "equity_curve": [],
        }
