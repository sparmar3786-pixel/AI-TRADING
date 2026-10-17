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
import { getBackendIdToken } from './firebase';

export const DEFAULT_SIGNAL_BACKEND = 'https://ai-trading-signals-api-production.up.railway.app';
export const DEFAULT_LEGACY_BACKEND = 'https://nse-algo-backend-final-production.up.railway.app';

// Instrument configurations
export const INDEX_CONFIG: Record<IndexSymbol, { name: string; lotSize: number; strikeStep: number }> = {
  NIFTY: { name: 'NIFTY 50', lotSize: 75, strikeStep: 50 },
  BANKNIFTY: { name: 'NIFTY BANK', lotSize: 30, strikeStep: 100 },
  FINNIFTY: { name: 'NIFTY FINANCIAL', lotSize: 65, strikeStep: 50 },
  MIDCPNIFTY: { name: 'NIFTY MIDCAP SELECT', lotSize: 120, strikeStep: 25 },
  SENSEX: { name: 'BSE SENSEX', lotSize: 20, strikeStep: 100 },
  BANKEX: { name: 'BSE BANKEX', lotSize: 30, strikeStep: 100 },
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

  public async getAuthHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      'Accept': 'application/json',
      'X-Device-Id': this.deviceId,
    };
    const token = await getBackendIdToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  private normalizeBaseUrl(url: string): string {
    const trimmed = (url || '').trim();
    if (!trimmed) return DEFAULT_SIGNAL_BACKEND;
    try {
      const parsed = new URL(trimmed);
      if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return DEFAULT_SIGNAL_BACKEND;
      if (parsed.search || parsed.hash || parsed.username || parsed.password) return DEFAULT_SIGNAL_BACKEND;
      const path = parsed.pathname.replace(/\/+$/, '');
      return parsed.origin + (path === '/' ? '' : path);
    } catch {
      return DEFAULT_SIGNAL_BACKEND;
    }
  }

  /** Only trusted, fresh, explicitly live exchange/broker snapshots may feed trading calculations. */
  public isFreshLiveMarketRow(row: MarketRow | undefined, maxAgeMs = 120000): boolean {
    if (!row || row.live !== true) return false;
    const timestamp = Date.parse(row.timestamp || '');
    const ageMs = Date.now() - timestamp;
    const source = String((row as MarketRow & { source?: string; data_source?: string }).source ||
      (row as MarketRow & { data_source?: string }).data_source || '').toLowerCase();
    const trustedSource = /angel|smartapi|nse|bse|broker|exchange/.test(source);
    const rowWithOptionalMarketFields = row as MarketRow & {
      session_high?: number; session_low?: number;
    };
    const requiredPriceValid = typeof row.ltp === 'number' && Number.isFinite(row.ltp) && row.ltp > 0;
    const optionalValues = [
      row.open, row.high, row.low, row.close, row.vwap, row.volume, row.pcr, row.max_pain, row.india_vix,
      rowWithOptionalMarketFields.session_high, rowWithOptionalMarketFields.session_low,
    ].filter(value => value !== undefined && value !== null);
    const optionalNumbersValid = optionalValues.every(value =>
      typeof value === 'number' && Number.isFinite(value) && value >= 0);
    const high = typeof row.high === 'number' ? row.high : rowWithOptionalMarketFields.session_high;
    const low = typeof row.low === 'number' ? row.low : rowWithOptionalMarketFields.session_low;
    const rangeValid = typeof high !== 'number' || typeof low !== 'number' ||
      (high >= low && row.ltp <= high && row.ltp >= low);
    return trustedSource && Number.isFinite(timestamp) && ageMs >= 0 && ageMs <= maxAgeMs &&
      requiredPriceValid && optionalNumbersValid && rangeValid;
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

  // The backend is the only authority allowed to promote a candidate to CONFIRMED.
  // This client validates timestamps and can only downgrade invalid/stale responses.
  public applyTenMinuteSignalGate(rawSignals: Record<string, SignalData>): Record<string, SignalData> {
    const now = Date.now();
    const result: Record<string, SignalData> = {};

    type ServerStability = {
      state?: string;
      required_minutes?: number;
      required_seconds?: number;
      elapsed_seconds?: number;
      remaining_seconds?: number;
      since_utc?: string;
      last_seen_utc?: string;
      candidate_key?: string;
    };
    const isBuy = (value: unknown): value is 'CALL BUY' | 'PUT BUY' =>
      value === 'CALL BUY' || value === 'PUT BUY';

    for (const [key, signal] of Object.entries(rawSignals)) {
      const updatedSignal: SignalData = { ...signal };
      const rawDecision = (updatedSignal.decision || 'WAIT').toUpperCase();
      const rawCandidate = (updatedSignal.candidate_decision || rawDecision).toUpperCase();
      const candidateDecision = isBuy(rawCandidate)
        ? rawCandidate
        : isBuy(rawDecision) ? rawDecision : 'WAIT';
      const wantsBuy = isBuy(candidateDecision);

      const rawValidation = updatedSignal.live_validation;
      const validation: NonNullable<SignalData['live_validation']> =
        rawValidation && typeof rawValidation === 'object'
          ? {
              verdict: rawValidation.verdict === 'PASS' || rawValidation.verdict === 'WARN' || rawValidation.verdict === 'FAIL'
                ? rawValidation.verdict : 'FAIL',
              decision: typeof rawValidation.decision === 'string' ? rawValidation.decision : 'WAIT',
              blocks: Array.isArray(rawValidation.blocks)
                ? rawValidation.blocks.filter((block): block is string => typeof block === 'string')
                : ['Live validation blocks are malformed; signal is not actionable.'],
              reasons: Array.isArray(rawValidation.reasons)
                ? rawValidation.reasons.filter((reason): reason is string => typeof reason === 'string')
                : undefined,
            }
          : {
              verdict: 'FAIL',
              decision: 'WAIT',
              blocks: ['Live validation missing; signal is not actionable.'],
            };

      const guards = Array.isArray(updatedSignal.guards) ? updatedSignal.guards : [];
      const signalTimestamp = Date.parse(updatedSignal.timestamp || '');
      const signalAgeMs = now - signalTimestamp;
      const signalFresh = Number.isFinite(signalTimestamp) && signalAgeMs >= 0 &&
        signalAgeMs <= 120000 && updatedSignal.data_fresh !== false;
      const validPositive = (value: unknown): value is number =>
        typeof value === 'number' && Number.isFinite(value) && value > 0;
      const validTradeNumbers = validPositive(updatedSignal.strike) &&
        validPositive(updatedSignal.entry) &&
        validPositive(updatedSignal.stop_loss) &&
        validPositive(updatedSignal.target) &&
        updatedSignal.stop_loss < updatedSignal.entry &&
        updatedSignal.target > updatedSignal.entry;
      const sideMatchesDecision =
        (candidateDecision === 'CALL BUY' && updatedSignal.option_side === 'CE') ||
        (candidateDecision === 'PUT BUY' && updatedSignal.option_side === 'PE');
      const candidateIsValid = wantsBuy && signalFresh && validTradeNumbers &&
        sideMatchesDecision && validation.verdict === 'PASS' && guards.length === 0;

      const stability = (updatedSignal.signal_stability || {}) as ServerStability;
      const requiredSeconds = typeof stability.required_seconds === 'number'
        ? stability.required_seconds
        : typeof stability.required_minutes === 'number'
          ? stability.required_minutes * 60 : 0;
      const sinceMs = typeof stability.since_utc === 'string' ? Date.parse(stability.since_utc) : Number.NaN;
      const lastSeenMs = typeof stability.last_seen_utc === 'string' ? Date.parse(stability.last_seen_utc) : Number.NaN;
      const serverElapsed = Number.isFinite(sinceMs) && Number.isFinite(lastSeenMs) && lastSeenMs >= sinceMs
        ? Math.floor((lastSeenMs - sinceMs) / 1000) : null;
      const lastSeenFresh = Number.isFinite(lastSeenMs) && Math.abs(now - lastSeenMs) <= 120000;
      const serverConfirmed = candidateIsValid &&
        rawDecision === candidateDecision &&
        stability.state === 'CONFIRMED' &&
        requiredSeconds >= 600 &&
        serverElapsed !== null &&
        serverElapsed >= requiredSeconds &&
        lastSeenFresh;

      updatedSignal.candidate_decision = candidateDecision;

      if (!candidateIsValid) {
        if (wantsBuy || isBuy(rawDecision)) {
          updatedSignal.decision = 'WAIT';
          const blocks = [...validation.blocks];
          if (validation.verdict !== 'PASS') {
            blocks.push('Server live validation is not PASS; candidate remains WAIT.');
          }
          if (guards.length > 0) blocks.push('Signal blocked by risk guards: ' + guards.join(', '));
          if (!signalFresh) blocks.push('Signal timestamp missing, stale, malformed, or in the future.');
          if (!validTradeNumbers) blocks.push('Strike, entry, stop-loss and target must be valid positive prices.');
          if (!sideMatchesDecision) blocks.push('Option side conflicts with the candidate decision.');
          validation.decision = 'WAIT';
          validation.verdict = validation.verdict === 'FAIL' ? 'FAIL' : 'WARN';
          validation.blocks = [...new Set(blocks)];
          updatedSignal.live_validation = validation;
        }
        updatedSignal.signal_stability = {
          state: 'NOT_ACTIONABLE',
          required_minutes: 10,
          server_confirmed: false,
        };
        result[key] = updatedSignal;
        continue;
      }

      if (serverConfirmed) {
        updatedSignal.decision = candidateDecision;
        updatedSignal.signal_stability = {
          state: 'CONFIRMED',
          required_minutes: 10,
          elapsed_seconds: serverElapsed ?? 600,
          remaining_seconds: 0,
          since_utc: stability.since_utc,
          server_confirmed: true,
        };
        result[key] = updatedSignal;
        continue;
      }

      // Keep the signal non-actionable until the response itself carries a valid
      // server-owned stability state and a >=600 second since/last-seen interval.
      updatedSignal.decision = 'WAIT';
      const serverConfirming =
        stability.state === 'CONFIRMING' &&
        requiredSeconds >= 600 &&
        serverElapsed !== null &&
        serverElapsed < requiredSeconds &&
        lastSeenFresh;
      updatedSignal.signal_stability = serverConfirming
        ? {
            state: 'CONFIRMING',
            required_minutes: 10,
            elapsed_seconds: Math.max(0, serverElapsed ?? 0),
            remaining_seconds: Math.max(0, requiredSeconds - (serverElapsed ?? 0)),
            since_utc: stability.since_utc,
            server_confirmed: false,
          }
        : {
            state: 'NOT_ACTIONABLE',
            required_minutes: 10,
            server_confirmed: false,
          };
      validation.decision = 'WAIT';
      validation.verdict = validation.verdict === 'FAIL' ? 'FAIL' : 'WARN';
      validation.blocks = [...new Set([
        ...validation.blocks,
        serverConfirming
          ? 'Waiting for the backend-owned 600-second confirmation gate.'
          : 'Backend has not supplied verifiable server-owned confirmation metadata.',
      ])];
      updatedSignal.live_validation = validation;
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
        headers: await this.getAuthHeaders(),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (resp.ok) {
        const data = sanitizeRepositoryLinks(await resp.json()) as any;
        const rawMarket = data.market && typeof data.market === 'object'
          ? data.market as Record<string, MarketRow>
          : {};
        const marketEntries = Object.entries(rawMarket);
        const freshMarketKeys = new Set(
          marketEntries.filter(([, row]) => this.isFreshLiveMarketRow(row)).map(([key]) => key.toUpperCase()),
        );
        const hasAnyFreshLiveMarket = marketEntries.length > 0 && freshMarketKeys.size > 0;
        const hasSignals = data.signals && Object.keys(data.signals).length > 0;

        // Keep individually verified symbols usable without allowing one stale
        // index to make every other healthy index disappear.
        if (hasAnyFreshLiveMarket && hasSignals) {
          const market = Object.fromEntries(marketEntries.map(([key, row]) => [
            key,
            this.isFreshLiveMarketRow(row) ? row : { ...row, live: false },
          ])) as Record<string, MarketRow>;
          const signals = this.applyTenMinuteSignalGate(data.signals);
          for (const [key, signal] of Object.entries(signals)) {
            if (!freshMarketKeys.has(key.toUpperCase())) {
              signals[key] = {
                ...signal,
                decision: 'WAIT',
                candidate_decision: 'WAIT',
                guards: [...new Set([...(signal.guards || []), 'MARKET_DATA_NOT_VERIFIED'])],
                live_validation: {
                  verdict: 'FAIL',
                  decision: 'WAIT',
                  blocks: [...new Set([
                    ...(signal.live_validation?.blocks || []),
                    'Market snapshot is stale or lacks a trusted source; signal forced to WAIT.',
                  ])],
                },
                signal_stability: { state: 'NOT_ACTIONABLE', required_minutes: 10 },
              };
            }
          }
          return {
            signals,
            market,
            isLive: marketEntries.every(([, row]) => this.isFreshLiveMarketRow(row)),
          };
        }
      }
    } catch (error) {
      // Do not synthesize prices/OI when the backend is unavailable.
      return {
        signals: this.generateFallbackSignals({}),
        market: {},
        isLive: false,
        error: error instanceof Error && error.name === 'AbortError'
          ? 'Signal backend timed out. No market values are displayed; all signals are WAIT.'
          : 'Signal backend unavailable. No market values are displayed; all signals are WAIT.',
      };
    }

    return {
      signals: this.generateFallbackSignals({}),
      market: {},
      isLive: false,
      error: 'Backend returned no verified fresh exchange snapshot. No market values are displayed; all signals are WAIT.',
    };
  }

  // Offline state deliberately contains no synthetic market prices or option-chain data.
  public generateFallbackMarket(): Record<string, MarketRow> {
    return {};
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

  public generateFallbackSignals(_market: Record<string, MarketRow>): Record<string, SignalData> {
    // Offline state is explicit WAIT for every supported index, with no synthetic prices.
    const generatedAt = new Date().toISOString();
    const indices: IndexSymbol[] = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX'];
    return Object.fromEntries(
      indices.map(key => [key, {
        index: key,
        decision: 'WAIT',
        candidate_decision: 'WAIT',
        regime: 'OFFLINE_UNVERIFIED',
        confidence: 0,
        guards: ['LIVE_BACKEND_UNAVAILABLE', 'MARKET_DATA_NOT_VERIFIED'],
        live_validation: {
          verdict: 'FAIL',
          decision: 'WAIT',
          blocks: ['Live market data and cloud validation are unavailable; no trade is actionable.'],
          reasons: ['No synthetic or cached price is accepted as a live quote.'],
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

  public getQuantLayers(signal?: SignalData): QuantLayerResult[] {
    type LayerEvidence = Record<string, unknown> & { pass?: unknown; score?: unknown; reason?: unknown; reason_code?: unknown };
    type EngineEvidence = { layers?: unknown; score_semantics?: unknown };
    const extended = signal as (SignalData & {
      quant_engine?: EngineEvidence;
      five_layer_engine?: EngineEvidence;
      layers?: unknown;
    }) | undefined;
    const engine = extended?.quant_engine ?? extended?.five_layer_engine;
    const rawLayers = engine?.layers && typeof engine.layers === 'object'
      ? engine.layers as Record<string, unknown>
      : extended?.layers && typeof extended.layers === 'object'
        ? extended.layers as Record<string, unknown> : {};
    const optionLayerName = 'option_selection' in rawLayers
      ? 'option_selection'
      : 'contract_selection' in rawLayers ? 'contract_selection' : 'option_selection';

    const definitions: Array<{ layer: number; name: string; key: string }> = [
      { layer: 1, name: 'Data Quality & Freshness', key: 'data_quality' },
      { layer: 2, name: 'Trend Alignment & Market Sentiment', key: 'trend_sentiment' },
      { layer: 3, name: 'Order Flow & Liquidity', key: 'order_flow' },
      { layer: 4, name: 'Option Contract Selection', key: optionLayerName },
      { layer: 5, name: 'Risk Levels & Stability Gate', key: 'risk_levels' },
    ];

    return definitions.map(definition => {
      const raw = rawLayers[definition.key];
      const evidence = raw && typeof raw === 'object' ? raw as LayerEvidence : null;
      const hasBooleanResult = typeof evidence?.pass === 'boolean';
      const status: QuantLayerResult['status'] = !hasBooleanResult
        ? 'UNAVAILABLE'
        : evidence.pass === true ? 'PASS' : 'FAIL';
      const score = typeof evidence?.score === 'number' &&
        Number.isFinite(evidence.score) && evidence.score >= 0 && evidence.score <= 100
        ? evidence.score : null;
      const detailParts: string[] = [];
      if (typeof evidence?.reason_code === 'string' && evidence.reason_code.trim()) {
        detailParts.push(evidence.reason_code.trim());
      }
      if (typeof evidence?.reason === 'string' && evidence.reason.trim()) {
        detailParts.push(evidence.reason.trim());
      }
      if (evidence) {
        const context = Object.entries(evidence)
          .filter(([name, value]) =>
            !['pass', 'score', 'reason', 'reason_code'].includes(name) &&
            (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') &&
            value !== '')
          .slice(0, 3)
          .map(([name, value]) => `${name}: ${String(value)}`);
        detailParts.push(...context);
      }
      if (!hasBooleanResult) {
        detailParts.push('The backend has not supplied this layer result; no local estimate is substituted.');
      } else if (detailParts.length === 0) {
        detailParts.push(status === 'PASS'
          ? 'Backend rule check passed.'
          : 'Backend rule check failed.');
      }
      detailParts.push('Rule-gate status is not a probability of profit.');
      return {
        layer: definition.layer,
        name: definition.name,
        status,
        score,
        detail: [...new Set(detailParts)].join(' • '),
      };
    });
  }

  public async getDiagnostics(): Promise<SystemDiagnostics> {
    try {
      const resp = await fetch(`${this.signalBackendUrl}/v1/system/diagnostics`, {
        headers: await this.getAuthHeaders(),
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
