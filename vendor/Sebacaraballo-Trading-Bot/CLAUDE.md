# Earnings Intelligence System

LLM-powered earnings intelligence trading system.  
Reads SEC 8-K filings → LLM extracts trade signals → executes paper trades.

## Project phases

| Phase | Status    | Description                                          |
|-------|-----------|------------------------------------------------------|
| 1     | ✅ Done   | Data ingestion — SEC 8-K filings + yfinance earnings |
| 2     | ✅ Done   | LLM signal extraction (Anthropic Claude API)         |
| 3     | ✅ Done   | Backtesting engine — replay signals vs historical prices |
| 4     | 🔜 Future | Alpaca paper trading integration                     |

## Quick start

```bash
cd earnings-intel
pip install -r requirements.txt
python main.py AAPL --filings 3 --preview
```

## File map

```
earnings-intel/
├── main.py                  CLI entry point (argparse + rich)
├── requirements.txt
├── earnings_intel.db        SQLite database (auto-created on first run)
├── data/                    Phase 1 — ingestion
│   ├── sec_client.py        SEC EDGAR API wrapper
│   ├── market_client.py     yfinance wrapper
│   └── fetcher.py           Orchestrator: calls SEC + yfinance, writes to DB
├── analysis/                Phase 2 — LLM signal extraction
│   ├── exhibit_fetcher.py   Pulls Exhibit 99.1 from the filing index
│   ├── prompt.py            System + user prompt templates
│   ├── llm_client.py        Anthropic Claude API client
│   └── pipeline.py          Orchestrates fetch → LLM → save
├── backtest/                Phase 3 — backtesting engine
│   ├── engine.py            Load signals → fetch prices → simulate → metrics
│   └── store.py             save_backtest_run / get_latest_backtest
├── api/                     Phase 5 — FastAPI backend
│   └── main.py              JSON endpoints over the SQLite DB
├── dashboard/               Phase 5 — React + TypeScript + Vite frontend
└── storage/
    └── database.py          SQLite schema + typed upsert/query methods
```

## CLI reference

```
python main.py TICKER [--filings N] [--preview] [--analyze] [--db PATH] [--verbose]
python main.py --backtest [--start DATE] [--threshold CONF] [--db PATH]

  TICKER          Stock ticker (AAPL, MSFT, NVDA …) — omit with --backtest
  --filings N     Number of 8-K filings to fetch (default 5)
  --preview       Print first 600 words of the most recent filing
  --analyze       Phase 2: fetch Exhibit 99.1 + extract LLM signals
  --backtest      Phase 3: replay stored signals against historical prices
  --start DATE    Backtest start date, ISO (default: 2024-01-01)
  --threshold C   Min signal confidence to trade in the backtest (default: 0.6)
  --db PATH       SQLite file path (default: earnings_intel.db)
  --verbose       Enable DEBUG logging
```

### Phase 3 backtest

```bash
# Backtest all stored bullish signals (confidence ≥ 0.6) since 2024-01-01
python main.py --backtest

# Custom window / threshold
python main.py --backtest --start 2024-01-01 --threshold 0.6
```

Strategy: buy bullish, high-confidence signals at the filing-date close, sell 5
trading days later (equal capital, sequentially compounded). Metrics — win rate,
Sharpe (annualized, 5-day hold), max drawdown, total return vs SPY — are computed
manually in `backtest/engine.py` (numpy only) and stored in `backtest_runs`. The
dashboard Backtest page reads them via `GET /api/backtest/latest`.

## Database schema (all phases)

```sql
companies       -- ticker, CIK, name, exchange, sector
earnings_dates  -- EPS estimates, actuals, surprise %     (Phase 1)
filings         -- raw HTML, cleaned text, word count     (Phase 1)
signals         -- LLM direction + confidence + reasoning (Phase 2)
backtest_runs   -- strategy parameters + P&L stats        (Phase 3)
trades          -- Alpaca order IDs, entry/exit prices    (Phase 4)
```

## Key design decisions

### SEC EDGAR rate limiting
- 150 ms minimum gap between all requests (enforced in `SECClient._throttle()`)
- `User-Agent: Sebastian Caraballo scarabal@purdue.edu` on every request  
- SEC policy allows up to 10 req/s; we stay well under at ~6.6 req/s

### Error handling
- Individual filing failures are **caught and logged**, never crash the pipeline
- Each failed filing is stored in SQLite with `fetch_status = 'failed'` and
  `error_message` set — re-run the CLI to retry only failed filings in a later phase
- yfinance failures return empty lists (service outage doesn't abort ingest)

### HTML cleaning (`SECClient._clean_html`)
- Removes `<script>`, `<style>`, `<meta>`, `<link>`, `<noscript>`, `<head>`
- Unwraps iXBRL namespace tags (`ix:nonNumeric`, `ix:nonFraction`) to preserve numbers
- Collapses whitespace, deduplicates consecutive identical lines
- Output is ready for direct LLM consumption in Phase 2

### Schema extensibility
- `signals` table pre-built with columns for LLM model, token counts,
  raw response, key metrics JSON blob
- `trades` table pre-built with Alpaca order ID, account ID, P&L, hold duration
- All tables use `created_at` / `updated_at` timestamps for audit trails

## Phase 2 hook points

When building Phase 2 (LLM signal extraction):

1. Query unflagged filings from `filings` where no `signals` row exists:
   ```python
   db._conn.execute("""
       SELECT f.id, f.cleaned_text, c.ticker
       FROM filings f
       JOIN companies c ON c.id = f.company_id
       LEFT JOIN signals s ON s.filing_id = f.id
       WHERE f.fetch_status = 'success' AND s.id IS NULL
   """)
   ```

2. Pass `cleaned_text` to the Claude API (use `claude-sonnet-4-6` or newer)

3. Parse the structured response and insert into `signals`:
   ```python
   db._conn.execute("""
       INSERT INTO signals (filing_id, company_id, signal_date, direction,
           confidence, reasoning, key_metrics, llm_model,
           llm_prompt_tokens, llm_completion_tokens, raw_llm_response)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
   """, ...)
   ```

## Phase 4 hook points (Alpaca)

- `trades.alpaca_order_id` maps to an Alpaca order UUID
- `trades.alpaca_account_id` supports multiple paper accounts
- `trades.status` lifecycle: `PENDING → OPEN → CLOSED | CANCELLED | REJECTED`
- Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` env vars (never hard-code)

## Environment

- Python 3.11+  
- SQLite 3.35+ (bundled with Python 3.11 on Windows)
- No API keys required for Phase 1
- Phase 2 needs: `ANTHROPIC_API_KEY`
- Phase 4 needs: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
