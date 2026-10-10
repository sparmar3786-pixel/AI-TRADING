// Shared TypeScript interfaces mirroring the FastAPI response shapes.

export type Sentiment = "bullish" | "bearish" | "neutral";
export type Direction = "LONG" | "SHORT" | "NEUTRAL";
export type GuidanceQuality =
  | "raised"
  | "maintained"
  | "lowered"
  | "withdrawn"
  | "none";
export type ManagementTone =
  | "optimistic"
  | "cautious"
  | "defensive"
  | "neutral";

// The parsed key_metrics JSON blob. Fields are optional/nullable because the
// LLM omits values that aren't present in the press release.
export interface KeyMetrics {
  guidance_quality?: GuidanceQuality | null;
  eps_beat?: boolean | null;
  revenue_beat?: boolean | null;
  management_tone?: ManagementTone | null;
  risk_flags?: string[];
  bull_case?: string;
  bear_case?: string;
  sentiment?: Sentiment;
}

export interface Signal {
  id: number;
  filing_id: number;
  ticker: string;
  filing_date: string;
  sentiment: Sentiment;
  confidence: number;
  direction: Direction;
  guidance_quality: GuidanceQuality | null;
  management_tone: ManagementTone | null;
  risk_flags: string[];
  key_metrics: KeyMetrics;
  bull_case: string;
  bear_case: string;
  reasoning: string;
  llm_model: string | null;
  created_at: string;
}

export interface Filing {
  id: number;
  ticker: string;
  filing_date: string;
  form_type: string;
  text_length: number;
  fetch_status: string;
  has_signal: boolean;
}

export interface FilingText {
  ticker: string;
  filing_date: string;
  text: string;
}

export interface Stats {
  companies: number;
  filings: number;
  signals: number;
  earnings_dates: number;
  analyzed_tickers: string[];
}

// Backtest (Phase 3). All ratio/return fields are decimal fractions (0.05 = 5%).
export interface BacktestTrade {
  signal_id: number;
  ticker: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  return_pct: number;
  direction: "long";
}

export interface EquityPoint {
  date: string;
  value: number;
}

export interface BacktestResults {
  id: number;
  run_date: string;
  start_date: string;
  confidence_threshold: number;
  total_signals_evaluated: number;
  trades_executed: number;
  trades_skipped: number;
  win_rate: number;
  avg_return_pct: number;
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  spy_return_pct: number;
  trades: BacktestTrade[];
  equity_curve: EquityPoint[];
}
