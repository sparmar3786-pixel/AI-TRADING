"""
main.py
-------
CLI entry point for the Earnings Intelligence System.

Usage
-----
    # Phase 1 — data ingest
    python main.py AAPL
    python main.py AAPL --filings 3 --preview

    # Phase 2 — LLM signal extraction (requires ANTHROPIC_API_KEY in .env)
    python main.py AAPL --analyze
    python main.py AAPL --filings 3 --analyze

    # Phase 3 — backtest stored signals against historical prices
    python main.py --backtest
    python main.py --backtest --start 2024-01-01 --threshold 0.6
"""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from data.fetcher import DataFetcher, IngestResult
from storage.database import Database

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

console = Console()

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """
    Construct the CLI argument parser.

    Returns:
        Configured ``ArgumentParser`` instance.
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Earnings Intelligence System — data ingest + LLM signal extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              python main.py AAPL
              python main.py MSFT --filings 3 --preview
              python main.py NVDA --filings 10 --db ./nvda.db
              python main.py AAPL --analyze
              python main.py AAPL --filings 3 --analyze
            """
        ),
    )
    parser.add_argument(
        "ticker",
        type=str,
        nargs="?",
        default=None,
        help="Stock ticker symbol (e.g. AAPL, MSFT, NVDA). Omit with --backtest.",
    )
    parser.add_argument(
        "--filings",
        type=int,
        default=5,
        metavar="N",
        help="Number of 8-K filings to fetch (default: 5)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the first 600 words of the most recent filing",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help=(
            "Run Phase 2: fetch Exhibit 99.1 for each filing and extract "
            "LLM signals (requires ANTHROPIC_API_KEY in .env). With no "
            "TICKER, analyzes pending filings across all companies."
        ),
    )
    parser.add_argument(
        "--max-llm",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Cap the number of LLM API calls per --analyze run; remaining "
            "filings stay pending for the next run (default: unlimited)"
        ),
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run Phase 3: replay stored signals against historical prices",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2024-01-01",
        metavar="DATE",
        help="Backtest start date, ISO format (default: 2024-01-01)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.6,
        metavar="CONF",
        help="Minimum signal confidence to trade in the backtest (default: 0.6)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="earnings_intel.db",
        metavar="PATH",
        help="SQLite database file path (default: earnings_intel.db)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return parser


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_header() -> None:
    """Print the application banner."""
    console.print(
        Panel.fit(
            "[bold cyan]Earnings Intelligence System[/bold cyan]  [dim]v0.1.0[/dim]\n"
            "[dim]Phase 1 — SEC EDGAR + yfinance Data Ingest[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )


def print_summary(result: IngestResult) -> None:
    """
    Render a summary table of what was stored.

    Args:
        result: Populated ``IngestResult`` from ``DataFetcher.ingest()``.
    """
    console.print()
    console.print(Rule("[bold]Summary[/bold]", style="cyan"))

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key",   style="dim", no_wrap=True)
    table.add_column("value", style="bold")

    table.add_row("Ticker",          result.ticker)
    table.add_row("Company",         result.company_name)
    table.add_row("CIK",             result.cik)
    table.add_row(
        "Filings stored",
        f"[green]{result.filings_ok}[/green] ok  "
        + (f"[red]{result.filings_failed}[/red] failed" if result.filings_failed else ""),
    )
    table.add_row("Earnings dates",  str(result.earnings_count))
    table.add_row("Database",        result.db_path)
    table.add_row("Elapsed",         f"{result.elapsed_seconds:.2f}s")

    console.print(table)


def print_filings_table(result: IngestResult) -> None:
    """
    Render a table of individual filing outcomes.

    Args:
        result: Populated ``IngestResult``.
    """
    if not result.filings:
        return

    console.print()
    console.print(Rule("[bold]Filing Detail[/bold]", style="dim"))

    tbl = Table(
        "Date",
        "Accession Number",
        "Form",
        "Words",
        "Status",
        box=None,
        padding=(0, 2),
        header_style="bold dim",
    )
    for f in result.filings:
        status_cell = "[green]✓ ok[/green]" if f.success else "[red]✗ failed[/red]"
        words_cell  = f"{f.word_count:,}" if f.word_count is not None else "—"
        tbl.add_row(f.filing_date, f.accession_number, f.form_type, words_cell, status_cell)

    console.print(tbl)


def print_signal(result, idx: int, total: int) -> None:
    """
    Render a single EarningsSignal to the console in a rich panel.

    Args:
        result: :class:`~analysis.pipeline.SignalResult` from the pipeline.
        idx:    1-based filing index (for the panel title).
        total:  Total number of filings being processed.
    """
    from analysis.pipeline import SignalResult  # local import avoids circular dep at module level

    if not result.success or result.signal is None:
        error_msg = result.error or "Unknown error"
        # Prefilter marks and budget deferrals are expected outcomes, not errors.
        if "marked" in error_msg or "deferred" in error_msg or "retry" in error_msg:
            console.print(
                Panel(
                    f"[yellow]Skipped:[/yellow] {error_msg}",
                    title=f"[dim]{result.ticker}  {result.filing_date}[/dim]",
                    border_style="yellow",
                )
            )
        else:
            console.print(
                Panel(
                    f"[red]✗ Failed:[/red] {error_msg}",
                    title=f"[dim]{result.ticker}  {result.filing_date}[/dim]",
                    border_style="red",
                )
            )
        return

    sig = result.signal

    # Colour-code direction
    dir_colour = {
        "LONG":    "green",
        "SHORT":   "red",
        "NEUTRAL": "yellow",
    }.get(sig.direction, "white")

    sentiment_icon = {
        "bullish": "📈",
        "bearish": "📉",
        "neutral": "➡️ ",
    }.get(sig.sentiment, "")

    # EPS / revenue badges
    def beat_badge(val) -> str:
        if val is True:
            return "[green]BEAT[/green]"
        if val is False:
            return "[red]MISS[/red]"
        return "[dim]N/A[/dim]"

    # Guidance badge
    guidance_colour = {
        "raised":    "green",
        "lowered":   "red",
        "withdrawn": "red",
        "maintained":"yellow",
        "none":      "dim",
    }.get(sig.guidance_quality, "dim")

    # Risk flags
    risks = "  ".join(f"[dim]•[/dim] {r}" for r in sig.risk_flags) if sig.risk_flags else "[dim]none[/dim]"

    body = (
        f"[bold {dir_colour}]{sig.direction}[/bold {dir_colour}]  "
        f"{sentiment_icon} [dim]confidence[/dim] {sig.confidence:.0%}  "
        f"  [dim]model[/dim] {sig.model}\n\n"
        f"[dim]EPS[/dim]      {beat_badge(sig.eps_beat)}   "
        f"[dim]Revenue[/dim]  {beat_badge(sig.revenue_beat)}   "
        f"[dim]Guidance[/dim]  [{guidance_colour}]{sig.guidance_quality}[/{guidance_colour}]   "
        f"[dim]Tone[/dim]  {sig.management_tone}\n\n"
        f"[bold]Reasoning[/bold]\n{sig.reasoning}\n\n"
        f"[green]▲ Bull case[/green]  {sig.bull_case}\n"
        f"[red]▼ Bear case[/red]  {sig.bear_case}\n\n"
        f"[bold dim]Risk flags[/bold dim]  {risks}\n\n"
        f"[dim]tokens: {sig.prompt_tokens} prompt / {sig.completion_tokens} completion[/dim]"
    )

    console.print(
        Panel(
            body,
            title=f"[bold]{result.ticker}[/bold]  [dim]{result.filing_date}[/dim]  "
                  f"[dim]({idx}/{total})[/dim]",
            border_style=dir_colour,
            padding=(1, 2),
        )
    )


def run_analysis(db: Database, ticker: str | None = None, max_llm: int | None = None) -> None:
    """
    Execute the Phase 2 signal extraction pipeline with a rich progress display.

    Args:
        db:      Open :class:`~storage.database.Database` instance.
        ticker:  Stock ticker symbol, or ``None`` to analyze pending filings
                 across all companies.
        max_llm: Optional cap on LLM API calls for this run.
    """
    from analysis.pipeline import SignalPipeline

    console.print()
    console.print(Rule("[bold]Phase 2 — LLM Signal Extraction[/bold]", style="cyan"))

    # Lazy import LLMClient so missing API key gives a clean error message
    try:
        from analysis.llm_client import LLMClient
        llm = LLMClient()
    except ValueError as exc:
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        return

    label = ticker or "all tickers"
    pipeline = SignalPipeline(db=db, llm_client=llm)
    pending = pipeline.get_pending_filings(ticker)

    if not pending:
        console.print(
            f"\n[yellow]⚠[/yellow]  No unanalyzed filings found for [bold]{label}[/bold].\n"
            "  Run ingestion first to fetch filings, or all filings may "
            "already have signals."
        )
        return

    budget_note = f" (max {max_llm} LLM calls)" if max_llm is not None else ""
    console.print(
        f"\nFound [bold]{len(pending)}[/bold] filing(s) to analyze for "
        f"[bold]{label}[/bold]{budget_note}.\n"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Analyzing {label}…", total=len(pending))

        def on_result(result, idx: int, total: int) -> None:
            progress.update(
                task,
                description=f"[cyan]{result.ticker}[/cyan]  {result.filing_date}  "
                             f"({idx}/{total})",
            )
            progress.advance(task)
            # Print result panel outside the progress bar
            progress.stop()
            print_signal(result, idx, total)
            progress.start()

        run = pipeline.run(ticker=ticker, max_llm=max_llm, on_result=on_result)

    console.print(
        f"\n[dim]Analyzed {run.total} filing(s): "
        f"[green]{run.succeeded} scored[/green], {run.skipped} without earnings "
        f"exhibit (marked), {run.deferred} deferred, [red]{run.failed} failed[/red], "
        f"{run.llm_calls} LLM call(s).[/dim]"
    )

    # Summary table (per-ticker view only)
    if ticker:
        run_summary_table(ticker, pending, pipeline)


def run_summary_table(ticker: str, pending: list, pipeline) -> None:
    """Print a compact signals summary table after the pipeline completes."""
    from analysis.pipeline import SignalPipeline

    console.print()
    console.print(Rule("[bold]Signals Summary[/bold]", style="dim"))

    company = pipeline._db.get_company(ticker)
    if company is None:
        return

    signals = pipeline._db.get_signals(company["id"])
    if not signals:
        return

    import json as _json

    tbl = Table(
        "Date", "Direction", "Conf.", "Guidance", "EPS", "Revenue", "Tone",
        box=None,
        padding=(0, 2),
        header_style="bold dim",
    )

    dir_colour = {"LONG": "green", "SHORT": "red", "NEUTRAL": "yellow"}

    for s in signals:
        km = _json.loads(s["key_metrics"] or "{}")
        direction = s["direction"] or "NEUTRAL"
        col = dir_colour.get(direction, "white")

        def _beat(val):
            if val is True:  return "[green]beat[/green]"
            if val is False: return "[red]miss[/red]"
            return "—"

        tbl.add_row(
            s["signal_date"],
            f"[{col}]{direction}[/{col}]",
            f"{s['confidence']:.0%}",
            km.get("guidance_quality", "—"),
            _beat(km.get("eps_beat")),
            _beat(km.get("revenue_beat")),
            km.get("management_tone", "—"),
        )

    console.print(tbl)
    console.print()


def print_preview(result: IngestResult, word_limit: int = 600) -> None:
    """
    Print a truncated preview of the most recent successful filing.

    Args:
        result:     Populated ``IngestResult``.
        word_limit: Maximum words to display (default 600).
    """
    if not result.latest_filing_text:
        console.print(
            "\n[yellow]⚠[/yellow]  No filing text available to preview."
        )
        return

    console.print()
    console.print(Rule("[bold]Filing Preview[/bold]", style="cyan"))

    # Metadata row
    meta_table = Table(show_header=False, box=None, padding=(0, 2))
    meta_table.add_column("k", style="dim")
    meta_table.add_column("v", style="bold")
    meta_table.add_row("Date",   result.latest_filing_date or "—")
    meta_table.add_row("Words",  f"{result.latest_filing_words:,}" if result.latest_filing_words else "—")
    meta_table.add_row("URL",    Text(result.latest_filing_url or "—", overflow="fold", style="dim cyan"))
    console.print(meta_table)
    console.print()

    # Text preview
    words = result.latest_filing_text.split()
    preview_text = " ".join(words[:word_limit])
    if len(words) > word_limit:
        preview_text += f"\n\n[dim]… {len(words) - word_limit:,} more words — run with --db to query the full text[/dim]"

    console.print(
        Panel(
            preview_text,
            border_style="dim",
            padding=(0, 1),
        )
    )


# ---------------------------------------------------------------------------
# Phase 3 — backtest
# ---------------------------------------------------------------------------

def print_backtest_results(results: dict) -> None:
    """Render a rich summary table of backtest metrics (fractions → %)."""
    console.print()
    console.print(Rule("[bold]Backtest Results[/bold]", style="cyan"))

    def _pct(v: float, signed: bool = True) -> str:
        return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"

    total_ret = results["total_return_pct"]
    spy_ret = results["spy_return_pct"]
    beat = total_ret > spy_ret
    ret_colour = "green" if total_ret >= 0 else "red"
    vs_colour = "green" if beat else "red"
    win_colour = "green" if results["win_rate"] > 0.5 else "yellow"
    sharpe = results["sharpe_ratio"]
    sharpe_colour = "green" if sharpe > 1.0 else "yellow" if sharpe >= 0.5 else "red"

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key", style="dim", no_wrap=True)
    table.add_column("value", style="bold")

    table.add_row("Signals evaluated", str(results["total_signals_evaluated"]))
    table.add_row("Trades executed", str(results["trades_executed"]))
    table.add_row("Trades skipped", str(results["trades_skipped"]))
    table.add_row("Win rate", f"[{win_colour}]{_pct(results['win_rate'], signed=False)}[/{win_colour}]")
    table.add_row("Avg return/trade", f"[{ret_colour}]{_pct(results['avg_return_pct'])}[/{ret_colour}]")
    table.add_row("Total return", f"[{ret_colour}]{_pct(total_ret)}[/{ret_colour}]")
    table.add_row("Sharpe ratio", f"[{sharpe_colour}]{sharpe:.2f}[/{sharpe_colour}]")
    table.add_row("Max drawdown", f"[red]{_pct(results['max_drawdown_pct'])}[/red]")
    table.add_row(
        "SPY (same period)",
        f"{_pct(spy_ret)}   [{vs_colour}]"
        f"({'beat' if beat else 'trailed'} by {abs(total_ret - spy_ret) * 100:.1f} pts)"
        f"[/{vs_colour}]",
    )

    console.print(
        Panel(table, title="[bold cyan]Backtest Results[/bold cyan]",
              border_style="cyan", padding=(1, 2))
    )


def run_backtest(db_path: str, start: str, threshold: float) -> None:
    """
    Execute the Phase 3 backtest, persist it, and print a summary table.

    Args:
        db_path:   SQLite path.
        start:     Backtest start date (ISO).
        threshold: Minimum confidence to trade.
    """
    from backtest.engine import BacktestEngine
    from backtest.store import save_backtest_run

    console.print()
    console.print(Rule("[bold]Phase 3 — Backtesting Engine[/bold]", style="cyan"))
    console.print()

    engine = BacktestEngine(db_path)
    results = engine.run(start_date=start, confidence_threshold=threshold)

    if results["trades_executed"] == 0:
        console.print(
            "\n[yellow]⚠[/yellow]  No trades were executed — nothing to persist.\n"
            "  Generate signals first with [dim]python main.py TICKER --analyze[/dim], "
            "or widen the date range / lower --threshold."
        )
        print_backtest_results(results)
        return

    run_id = save_backtest_run(engine._db, results)
    print_backtest_results(results)
    console.print(f"\n[dim]Saved backtest run #{run_id} to the database.[/dim]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Parse CLI arguments, run the ingestion pipeline, and render results.

    Exits with code 1 on unrecoverable errors (e.g. unknown ticker).
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print_header()

    # ── Phase 3 — backtest mode (no ticker required) ──────────────────────
    if args.backtest:
        try:
            run_backtest(args.db, args.start, args.threshold)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            sys.exit(130)
        except Exception as exc:
            console.print(f"\n[bold red]Backtest error:[/bold red] {exc}")
            logger.exception("Unhandled exception in run_backtest()")
            sys.exit(1)
        console.print()
        return

    # ── Phase 2 across all tickers (no ingestion) ─────────────────────────
    if args.analyze and not args.ticker:
        try:
            db = Database(args.db)
        except Exception as exc:
            console.print(f"\n[bold red]Error:[/bold red] Could not open database: {exc}")
            sys.exit(1)
        try:
            run_analysis(db, ticker=None, max_llm=args.max_llm)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            sys.exit(130)
        except Exception as exc:
            console.print(f"\n[bold red]Analysis error:[/bold red] {exc}")
            logger.exception("Unhandled exception in run_analysis()")
            sys.exit(1)
        console.print()
        return

    # ── Phase 1 requires a ticker ─────────────────────────────────────────
    if not args.ticker:
        console.print(
            "\n[bold red]Error:[/bold red] a TICKER is required "
            "(or pass --backtest / --analyze for the ticker-less modes).\n"
            "  e.g. [dim]python main.py AAPL --analyze[/dim]"
        )
        sys.exit(1)

    # Initialise database and fetcher
    try:
        db = Database(args.db)
    except Exception as exc:
        console.print(f"\n[bold red]Error:[/bold red] Could not open database: {exc}")
        sys.exit(1)

    fetcher = DataFetcher(db)

    # Run ingestion pipeline
    try:
        result = fetcher.ingest(args.ticker.upper(), args.filings)
    except ValueError as exc:
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {exc}")
        logger.exception("Unhandled exception in ingest()")
        sys.exit(1)

    # Render results
    print_summary(result)
    print_filings_table(result)

    if args.preview:
        print_preview(result)

    # Phase 2 — LLM signal extraction
    if args.analyze:
        run_analysis(db, ticker=args.ticker.upper(), max_llm=args.max_llm)

    console.print()


if __name__ == "__main__":
    main()
