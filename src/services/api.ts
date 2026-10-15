import {
  IndexSymbol,
  SignalData,
  MarketRow,
  OptionChainRow,
  SystemDiagnostics,
  TechnicalIndicators,
  QuantLayerResult,
} from '../types/market';
import { sanitizeRepositoryLinks } from './repositoryLinkFilter';

export const DEFAULT_SIGNAL_BACKEND = 'https://ai-trading-signals-api-production.up.railway.app';
export const DEFAULT_LEGACY_BACKEND = 'https://nse-algo-backend-final-production.up.railway.app';

// Instrument configurations
export const INDEX_CONFIG: Record<IndexSymbol, { name: string; lotSize: number; strikeStep: number; basePrice: number }> = {
  NIFTY: { name: 'NIFTY 50', lotSize: 75, strikeStep: 50, basePrice: 24865.50 },
  BANKNIFTY: { name: 'NIFTY BANK', lotSize: 30, strikeStep: 100, basePrice: 51420.20 },
  FINNIFTY: { name: 'NIFTY FINANCIAL', lotSize: 65, strikeStep: 50, basePrice: 23680.10 },
  MIDCPNIFTY: { name: 'NIFTY MIDCAP SELECT', lotSize: 120, strikeStep: 25, basePrice: 12990.40 },
  SENSEX: { name: 'BSE SENSEX', lotSize: 20, strikeStep: 100, basePrice: 81750.60 },
  BANKEX: { name: 'BSE BANKEX', lotSize: 30, strikeStep: 100, basePrice: 58180.30 },
};



class ApiService {
  private signalBackendUrl: string = DEFAULT_SIGNAL_BACKEND;
  private legacyBackendUrl: string = DEFAULT_LEGACY_BACKEND;
  private deviceId: string = '';

  constructor() {
    this.signalBackendUrl = this.normalizeBaseUrl(
      localStorage.getItem('fresh_signal_backend_url') || DEFAULT_SIGNAL_BACKEND,
    );
    this.legacyBackendUrl = this.normalizeBaseUrl(
      localStorage.getItem('fresh_legacy_backend_url') || DEFAULT_LEGACY_BACKEND,
    );
    this.deviceId = this.getOrCreateDeviceId();
  }

  private normalizeBaseUrl(url: string): string {
    const trimmed = (url || '').trim();
    if (!trimmed) return DEFAULT_SIGNAL_BACKEND;
    try {
      return new URL(trimmed).origin;
    } catch {
      return trimmed.replace(/\/+$/, '');
    }
  }

  private getOrCreateDeviceId(): string {
    let id = localStorage.getItem('fresh_device_id');
    // Railway backend requires 43–128 URL-safe characters
    if (!id || id.length < 43 || id.length > 128) {
      const part1 = Math.random().toString(36).substring(2).padEnd(12, '0');
      const part2 = Math.random().toString(36).substring(2).padEnd(12, '0');
      const part3 = Date.now().toString(36).padEnd(10, '0');
      id = `fresh_android_device_${part1}_${part2}_${part3}`; // ~50 chars, url-safe
      localStorage.setItem('fresh_device_id', id);
    }
    return id;
  }

  public getDeviceId(): string {
    return this.deviceId;
  }

  public getSignalBackend(): string {
    return this.signalBackendUrl;
  }

  public setSignalBackend(url: string) {
    this.signalBackendUrl = this.normalizeBaseUrl(url);
    localStorage.setItem('fresh_signal_backend_url', this.signalBackendUrl);
  }

  public getLegacyBackend(): string {
    return this.legacyBackendUrl;
  }

  public setLegacyBackend(url: string) {
    this.legacyBackendUrl = this.normalizeBaseUrl(url);
    localStorage.setItem('fresh_legacy_backend_url', this.legacyBackendUrl);
  }

  // Check whether the Indian equity market is open right now in IST
  public getMarketOpenStatus(): { equityOpen: boolean; istTime: string } {
    const now = new Date();
    // Convert to IST (UTC + 5:30)
    const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
    const istDate = new Date(utc + (3600000 * 5.5));
    
    const day = istDate.getDay();
    const hours = istDate.getHours();
    const minutes = istDate.getMinutes();
    const totalMinutes = hours * 60 + minutes;

    const isWeekend = day === 0 || day === 6; // Sunday or Saturday
    // Equity: 09:15 to 15:30 IST
    const equityOpen = !isWeekend && totalMinutes >= (9 * 60 + 15) && totalMinutes <= (15 * 60 + 30);

    const istTimeStr = istDate.toLocaleTimeString('en-IN', { hour12: true, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' IST';

    return { equityOpen, istTime: istTimeStr };
  }

  // 10-Minute Signal Stability Gate
  public applyTenMinuteSignalGate(rawSignals: Record<string, SignalData>): Record<string, SignalData> {
    const now = Date.now();
    const result: Record<string, SignalData> = {};

    for (const [key, signal] of Object.entries(rawSignals)) {
      const index = key.toUpperCase();
      const updatedSignal = { ...signal };
      const decision = (updatedSignal.decision || 'WAIT').toUpperCase();
      const validation = updatedSignal.live_validation ?? {
        verdict: 'FAIL' as const,
        decision: 'WAIT',
        blocks: ['Live validation missing; signal is not actionable.'],
      };
      const guards = updatedSignal.guards || [];

      const isCandidate = (decision === 'CALL BUY' || decision === 'PUT BUY') &&
        updatedSignal.strike &&
        updatedSignal.option_side &&
        updatedSignal.entry &&
        updatedSignal.stop_loss &&
        updatedSignal.target &&
        validation.verdict === 'PASS' &&
        guards.length === 0;

      const storageKey = `ai_trading_signal_gate_${index}`;

      if (!isCandidate) {
        localStorage.removeItem(storageKey);
        updatedSignal.signal_stability = {
          state: 'NOT_ACTIONABLE',
          required_minutes: 10,
        };
        result[key] = updatedSignal;
        continue;
      }

      const candidateKey = `${decision}|${updatedSignal.strike}|${updatedSignal.option_side}`;
      const savedRaw = localStorage.getItem(storageKey);
      let saved: { candidate: string; since_utc: number; last_seen_utc: number } | null = null;

      if (savedRaw) {
        try {
          saved = JSON.parse(savedRaw);
        } catch (_) {
          saved = null;
        }
      }

      const gapTooLong = !saved || (now - saved.last_seen_utc) > 60000; // gap > 60 sec

      if (!saved || saved.candidate !== candidateKey || gapTooLong) {
        saved = {
          candidate: candidateKey,
          since_utc: now,
          last_seen_utc: now,
        };
      } else {
        saved.last_seen_utc = now;
      }

      localStorage.setItem(storageKey, JSON.stringify(saved));

      const elapsed = Math.floor((now - saved.since_utc) / 1000);
      const remaining = Math.max(0, 600 - elapsed);
      updatedSignal.candidate_decision = decision;

      if (elapsed < 600) {
        // Enforce WAIT during confirmation window
        updatedSignal.decision = 'WAIT';
        updatedSignal.signal_stability = {
          state: 'CONFIRMING',
          required_minutes: 10,
          elapsed_seconds: elapsed,
          remaining_seconds: remaining,
          since_utc: new Date(saved.since_utc).toISOString(),
        };
        const updatedValidation = { ...validation };
        updatedValidation.decision = 'WAIT';
        updatedValidation.verdict = 'WARN';
        const blocks = [...updatedValidation.blocks];
        if (!blocks.some(b => b.includes('10-minute stability gate'))) {
          blocks.push(`10-minute stability gate: candidate active for ${elapsed}s / 600s`);
        }
        updatedValidation.blocks = blocks;
        updatedSignal.live_validation = updatedValidation;
      } else {
        // Confirmed stable after 10 full minutes
        updatedSignal.decision = decision as any;
        updatedSignal.signal_stability = {
          state: 'CONFIRMED',
          required_minutes: 10,
          elapsed_seconds: elapsed,
          remaining_seconds: 0,
          since_utc: new Date(saved.since_utc).toISOString(),
        };
      }

      result[key] = updatedSignal;
    }

    return result;
  }

  // Fetch signals with live Railway fallback
  public async fetchSignals(): Promise<{
    signals: Record<string, SignalData>;
    market: Record<string, MarketRow>;
    isLive: boolean;
    error?: string;
  }> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 6000);

      const resp = await fetch(`${this.signalBackendUrl}/v1/signals`, {
        headers: {
          'Accept': 'application/json',
          'X-Device-Id': this.deviceId,
        },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (resp.ok) {
        const data = sanitizeRepositoryLinks(await resp.json()) as any;
        const rows = data.market && typeof data.market === 'object'
          ? Object.values(data.market) as MarketRow[]
          : [];
        const hasFreshLiveMarket = rows.length > 0 && rows.every(row => {
          const timestamp = Date.parse(row.timestamp || '');
          const ageMs = Date.now() - timestamp;
          return row.live === true && Number.isFinite(timestamp) && ageMs >= 0 && ageMs <= 120000;
        });
        const hasSignals = data.signals && Object.keys(data.signals).length > 0;

        // A 200 response is not proof of fresh broker data. Fail closed if
        // market rows lack an explicit live marker or fresh exchange timestamp.
        if (hasFreshLiveMarket && hasSignals) {
          return {
            signals: this.applyTenMinuteSignalGate(data.signals),
            market: data.market,
            isLive: true,
          };
        }
      }
    } catch {
      // Never describe locally generated preview values as live market data.
      const fallbackMarket = this.generateFallbackMarket();
      const safeMarket = Object.fromEntries(
        Object.entries(fallbackMarket).map(([key, row]) => [key, { ...row, live: false }]),
      ) as Record<string, MarketRow>;
      return {
        signals: this.generateFallbackSignals(safeMarket),
        market: safeMarket,
        isLive: false,
        error: 'Live backend unavailable. Display values are offline preview only; all trade signals are WAIT.',
      };
    }

    const fallbackMarket = this.generateFallbackMarket();
    const safeMarket = Object.fromEntries(
      Object.entries(fallbackMarket).map(([key, row]) => [key, { ...row, live: false }]),
    ) as Record<string, MarketRow>;
    return {
      signals: this.generateFallbackSignals(safeMarket),
      market: safeMarket,
      isLive: false,
      error: 'Live backend returned no fresh exchange-timestamped market snapshot. Trade signals are WAIT.',
    };
  }

  // Generate realistic high-fidelity market data
  public generateFallbackMarket(): Record<string, MarketRow> {
    const market: Record<string, MarketRow> = {};
    const indices: IndexSymbol[] = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX'];

    indices.forEach(idx => {
      const cfg = INDEX_CONFIG[idx];
      // small deterministic drift based on current minute
      const minute = new Date().getMinutes();
      const driftPercent = Math.sin(minute / 5 + idx.length) * 0.45 + (idx === 'NIFTY' ? 0.32 : -0.15);
      const ltp = Number((cfg.basePrice * (1 + driftPercent / 100)).toFixed(2));
      const change = Number((ltp - cfg.basePrice).toFixed(2));
      const change_percent = Number((change / cfg.basePrice * 100).toFixed(2));

      const option_chain = this.generateOptionChain(idx, ltp, cfg.strikeStep);

      market[idx] = {
        symbol: idx,
        ltp,
        change,
        change_percent,
        open: Number((cfg.basePrice * 0.998).toFixed(2)),
        high: Number((Math.max(ltp, cfg.basePrice) * 1.004).toFixed(2)),
        low: Number((Math.min(ltp, cfg.basePrice) * 0.995).toFixed(2)),
        close: cfg.basePrice,
        vwap: Number((ltp * 0.9992).toFixed(2)),
        volume: 4500000 + Math.floor(Math.sin(minute) * 1000000),
        pcr: Number((1.08 + Math.cos(minute / 3) * 0.18).toFixed(2)),
        max_pain: Math.round(ltp / cfg.strikeStep) * cfg.strikeStep,
        india_vix: 13.85,
        trend: change >= 0 ? 'BULLISH' : 'BEARISH',
        option_chain,
        timestamp: new Date().toISOString(),
        live: false, // Synthetic preview data is never live.
      };
    });

    return market;
  }

  public generateOptionChain(symbol: IndexSymbol, spotPrice: number, strikeStep: number): OptionChainRow[] {
    const atmStrike = Math.round(spotPrice / strikeStep) * strikeStep;
    const strikes: OptionChainRow[] = [];

    for (let i = -7; i <= 7; i++) {
      const strike = atmStrike + i * strikeStep;
      const isAtm = strike === atmStrike;
      const distFromSpot = strike - spotPrice;

      // Realistic Call Price (Intrinsic + Extrinsic)
      const ceIntrinsic = Math.max(0, spotPrice - strike);
      const ceExtrinsic = Math.max(12, 180 - Math.abs(distFromSpot) * 0.22);
      const ce_ltp = Number((ceIntrinsic + ceExtrinsic).toFixed(2));

      // Realistic Put Price
      const peIntrinsic = Math.max(0, strike - spotPrice);
      const peExtrinsic = Math.max(12, 180 - Math.abs(distFromSpot) * 0.22);
      const pe_ltp = Number((peIntrinsic + peExtrinsic).toFixed(2));

      // Open Interest bell curves
      const baseOI = 450000 - Math.abs(i) * 32000;
      const ce_oi = Math.max(25000, baseOI + (i > 0 ? 120000 : 0));
      const pe_oi = Math.max(25000, baseOI + (i < 0 ? 140000 : 0));

      strikes.push({
        strike,
        is_atm: isAtm,
        ce_ltp,
        ce_change: Number(((spotPrice > strike ? 1 : -1) * (15 - Math.abs(i))).toFixed(2)),
        ce_oi,
        ce_oi_change: Math.floor(ce_oi * 0.08 * (i >= 0 ? 1 : -1)),
        ce_volume: Math.floor(ce_oi * 1.8),
        ce_iv: Number((14.2 + Math.abs(i) * 0.3).toFixed(1)),
        pe_ltp,
        pe_change: Number(((spotPrice < strike ? 1 : -1) * (15 - Math.abs(i))).toFixed(2)),
        pe_oi,
        pe_oi_change: Math.floor(pe_oi * 0.09 * (i <= 0 ? 1 : -1)),
        pe_volume: Math.floor(pe_oi * 1.7),
        pe_iv: Number((15.1 + Math.abs(i) * 0.3).toFixed(1)),
      });
    }

    return strikes;
  }

  public generateFallbackSignals(market: Record<string, MarketRow>): Record<string, SignalData> {
    // Offline preview data must never create a synthetic CALL/PUT recommendation.
    const generatedAt = new Date().toISOString();
    return Object.fromEntries(
      Object.keys(market).map(key => [key, {
        index: key,
        decision: 'WAIT',
        candidate_decision: 'WAIT',
        regime: 'OFFLINE_UNVERIFIED',
        confidence: 0,
        guards: ['LIVE_BACKEND_UNAVAILABLE', 'MARKET_DATA_NOT_VERIFIED'],
        live_validation: {
          verdict: 'WARN',
          decision: 'WAIT',
          blocks: ['Live market data and cloud validation are unavailable; no trade is actionable.'],
          reasons: ['Offline preview values are not exchange quotes.'],
        },
        reasons: ['Backend unavailable or snapshot stale. Reconnect before reviewing any trade.'],
        timestamp: generatedAt,
        data_fresh: false,
      } as SignalData]),
    );
  }

  public getTechnicalIndicators(ltp: number): TechnicalIndicators {
    return {
      ema8: Number((ltp * 1.0008).toFixed(2)),
      ema13: Number((ltp * 1.0002).toFixed(2)),
      ema21: Number((ltp * 0.9991).toFixed(2)),
      ema50: Number((ltp * 0.9975).toFixed(2)),
      ema200: Number((ltp * 0.9920).toFixed(2)),
      rsi14: 58.4,
      macd: {
        macd: 18.4,
        signal: 12.1,
        histogram: 6.3,
      },
      supertrend: {
        direction: 'BULLISH',
        value: Number((ltp * 0.996).toFixed(2)),
      },
      atr14: Number((ltp * 0.0065).toFixed(2)),
      bollinger: {
        upper: Number((ltp * 1.006).toFixed(2)),
        middle: Number((ltp).toFixed(2)),
        lower: Number((ltp * 0.994).toFixed(2)),
      },
      vwap: Number((ltp * 0.9994).toFixed(2)),
    };
  }

  public getQuantLayers(): QuantLayerResult[] {
    const detail = 'Live quant calculation unavailable. Waiting for verified backend results.';
    return [
      { layer: 1, name: 'Trend Alignment & Moving Averages', status: 'UNAVAILABLE', score: null, weight: 25, detail },
      { layer: 2, name: 'Momentum & Volatility Filter', status: 'UNAVAILABLE', score: null, weight: 20, detail },
      { layer: 3, name: 'Price Action & Breakout Volume', status: 'UNAVAILABLE', score: null, weight: 25, detail },
      { layer: 4, name: 'Options Open Interest & PCR Flow', status: 'UNAVAILABLE', score: null, weight: 20, detail },
      { layer: 5, name: 'Execution Guard & Slippage Filter', status: 'UNAVAILABLE', score: null, weight: 10, detail },
    ];
  }

  public async getDiagnostics(): Promise<SystemDiagnostics> {
    try {
      const resp = await fetch(`${this.signalBackendUrl}/v1/system/diagnostics`, {
        headers: { 'X-Device-Id': this.deviceId },
      });
      if (resp.ok) return sanitizeRepositoryLinks(await resp.json()) as SystemDiagnostics;
    } catch (_) {}

    return {
      backend_worker: {
        cycle_age_seconds: null,
        cycle_fresh: false,
        uptime_hours: null,
      },
      angel_one: {
        authenticated: false,
        stream_open: false,
        last_tick_age_seconds: null,
        client_code: 'Not verified',
      },
      market_data: {
        snapshot_count: 0,
        fresh_snapshot_count: 0,
        live_snapshot_count: 0,
        ticks_per_second: 0,
      },
      ai_provider: {
        configured: false,
        nvidia_status: 'unavailable',
        openrouter_status: 'unavailable',
        model: 'unavailable',
      },
    };
  }
}

export const apiService = new ApiService();
