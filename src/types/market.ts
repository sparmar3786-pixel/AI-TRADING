export type IndexSymbol = 'NIFTY' | 'BANKNIFTY' | 'FINNIFTY' | 'MIDCPNIFTY' | 'SENSEX' | 'BANKEX';

export type SignalDecision = 'CALL BUY' | 'PUT BUY' | 'WAIT' | 'HOLD';

export interface SignalStability {
  state: 'CONFIRMING' | 'CONFIRMED' | 'NOT_ACTIONABLE' | 'STALE_OFFLINE';
  required_minutes: number;
  elapsed_seconds?: number;
  remaining_seconds?: number;
  since_utc?: string;
  server_confirmed?: boolean;
}

export interface LiveValidation {
  verdict: 'PASS' | 'WARN' | 'FAIL';
  decision: string;
  blocks: string[];
  reasons?: string[];
}

export interface SignalData {
  index: string;
  decision: SignalDecision;
  candidate_decision?: string;
  strike?: number;
  option_side?: 'CE' | 'PE';
  entry?: number;
  stop_loss?: number;
  target?: number;
  risk_reward?: string;
  confidence?: number;
  regime?: string;
  signal_stability?: SignalStability;
  live_validation?: LiveValidation;
  guards?: string[];
  reasons?: string[];
  timestamp?: string;
  data_fresh?: boolean;
}

export interface OptionChainRow {
  strike: number;
  is_atm?: boolean;
  ce_ltp: number;
  ce_change: number;
  ce_oi: number;
  ce_oi_change: number;
  ce_volume: number;
  ce_iv: number;
  pe_ltp: number;
  pe_change: number;
  pe_oi: number;
  pe_oi_change: number;
  pe_volume: number;
  pe_iv: number;
}

export interface MarketRow {
  symbol: string;
  ltp: number;
  change: number;
  change_percent: number;
  open: number;
  high: number;
  low: number;
  close: number;
  vwap: number;
  volume: number;
  pcr: number;
  max_pain: number;
  india_vix: number;
  trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  option_chain?: OptionChainRow[];
  timestamp: string;
  live: boolean;
  /** Explicit upstream source; required for trading eligibility. */
  source?: string;
  data_source?: string;
  day_move_pct?: number;
  session_high?: number;
  session_low?: number;
  indicators?: { vwap?: number };
}


export interface TechnicalIndicators {
  ema8: number;
  ema13: number;
  ema21: number;
  ema50: number;
  ema200: number;
  rsi14: number;
  macd: { macd: number; signal: number; histogram: number };
  supertrend: { direction: 'BULLISH' | 'BEARISH'; value: number };
  atr14: number;
  bollinger: { upper: number; middle: number; lower: number };
  vwap: number;
}

export interface QuantLayerResult {
  layer: number;
  name: string;
  status: 'PASS' | 'WARN' | 'FAIL' | 'UNAVAILABLE';
  score: number | null;
  weight?: number;
  detail: string;
}

export interface PaperTrade {
  id: string;
  timestamp: string;
  symbol: string;
  option_name: string;
  side: 'CE' | 'PE';
  action: 'BUY' | 'SELL';
  lots: number;
  quantity: number;
  entry_price: number;
  current_price: number;
  stop_loss: number;
  target: number;
  pnl: number;
  pnl_percent: number;
  status: 'OPEN' | 'CLOSED' | 'CANCELLED';
  mark_status?: 'WAITING_FOR_LIVE_OPTION_QUOTE' | 'LIVE_OPTION_QUOTE' | 'UNAVAILABLE';
  mark_timestamp?: string;
  closed_at?: string;
  exit_price?: number;
}

export interface SystemDiagnostics {
  backend_worker: {
    cycle_age_seconds: number | null;
    cycle_fresh: boolean;
    uptime_hours: number | null;
  };
  angel_one: {
    authenticated: boolean;
    stream_open: boolean;
    last_tick_age_seconds: number | null;
    client_code: string;
  };
  market_data: {
    snapshot_count: number;
    fresh_snapshot_count: number;
    live_snapshot_count: number;
    ticks_per_second: number;
  };
  ai_provider: {
    configured: boolean;
    nvidia_status: string;
    openrouter_status: string;
    model: string;
  };
}
