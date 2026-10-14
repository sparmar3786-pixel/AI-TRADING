import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService } from '../services/api';
import { AlertTriangle, RefreshCw, Shield, BarChart2 } from 'lucide-react';

type Candle = { timestamp: string; open: number; high: number; low: number; close: number; volume: number };
type CandleResponse = { status?: string; source?: string; count?: number; candles?: Candle[]; last_candle?: string | null };
type Zone = { type?: string; top?: number; bottom?: number; index?: number };
type SmcResult = {
  instrument?: string;
  signal?: string;
  bias?: string;
  entry?: number | null;
  stop_loss?: number | null;
  target_reference?: string | null;
  htf?: { candles?: number; bias?: string; bos?: boolean; choch?: boolean };
  mtf?: { candles?: number; bias?: string; bos?: boolean; choch?: boolean };
  ltf?: { candles?: number; last_close?: number | null; order_blocks?: Zone[]; fvgs?: Zone[]; bsl?: number[]; ssl?: number[]; poi?: Zone | null };
  reasons?: string[];
  execution_allowed?: boolean;
  note?: string;
  killzone_status?: { window?: string | null; effective_active?: boolean };
};
const base = () => apiService.getSignalBackend().replace(/\/+$/, '');
const headers = () => ({ Accept: 'application/json', 'X-Device-Id': apiService.getDeviceId() });
const fmt = (value?: number | null) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—';
const timeText = (value?: string | null) => {
  if (!value) return '—';
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : value;
};

export const SmcChartPage: React.FC = () => {
  const { selectedIndex, market } = useTrading();
  const currentMarket = market[selectedIndex];
  const ageMs = currentMarket?.timestamp ? Date.now() - Date.parse(currentMarket.timestamp) : Number.POSITIVE_INFINITY;
  const marketFresh = Boolean(currentMarket?.live === true && Number.isFinite(ageMs) && ageMs >= 0 && ageMs <= 120000);
  const [timeframe, setTimeframe] = useState<'ONE_MINUTE' | 'FIVE_MINUTE' | 'FIFTEEN_MINUTE' | 'ONE_HOUR'>('FIVE_MINUTE');
  const [strategy, setStrategy] = useState<'Guardeer' | 'Inner Circle'>('Guardeer');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<SmcResult | null>(null);
  const [htfCandles, setHtfCandles] = useState<Candle[]>([]);
  const [mtfCandles, setMtfCandles] = useState<Candle[]>([]);
  const [ltfCandles, setLtfCandles] = useState<Candle[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const loadCandles = useCallback(async (interval: string, days: number): Promise<CandleResponse> => {
    const query = new URLSearchParams({ index: selectedIndex, interval, days: String(days) });
    const response = await fetch(`${base()}/v1/market/candles?${query.toString()}`, { headers: headers() });
    const body = await response.json();
    if (!response.ok) {
      const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`;
      throw new Error(detail);
    }
    if (!Array.isArray(body?.candles)) throw new Error('Candle endpoint returned an invalid payload.');
    return body as CandleResponse;
  }, [selectedIndex]);

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    try {
      const [htf, mtf, ltf] = await Promise.all([
        loadCandles('ONE_DAY', 7),
        loadCandles('ONE_HOUR', 7),
        loadCandles(timeframe, 3),
      ]);
      const htfRows = htf.candles || [];
      const mtfRows = mtf.candles || [];
      const ltfRows = ltf.candles || [];
      setHtfCandles(htfRows);
      setMtfCandles(mtfRows);
      setLtfCandles(ltfRows);
      setLastUpdated(new Date().toISOString());

      if (!htfRows.length || !mtfRows.length || !ltfRows.length) {
        setError('Angel One returned no historical candles for one or more timeframes. SMC levels are not generated from empty data.');
        return;
      }

      const response = await fetch(`${base()}/v1/smc/analyze`, {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instrument: selectedIndex,
          htf_candles: htfRows,
          mtf_candles: mtfRows,
          ltf_candles: ltfRows,
          strategy_format: strategy,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      setAnalysis(body as SmcResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'SMC candle/analysis request failed');
    } finally {
      setLoading(false);
    }
  }, [loadCandles, selectedIndex, strategy, timeframe]);

  useEffect(() => { void runAnalysis(); }, [runAnalysis]);

  const chartCandles = useMemo(() => ltfCandles.slice(-32), [ltfCandles]);
  const chartBounds = useMemo(() => {
    if (!chartCandles.length) return { min: 0, max: 1, range: 1 };
    const min = Math.min(...chartCandles.map(c => c.low));
    const max = Math.max(...chartCandles.map(c => c.high));
    return { min, max, range: Math.max(max - min, 0.0001) };
  }, [chartCandles]);
  const orderBlocks = analysis?.ltf?.order_blocks || [];
  const fvgs = analysis?.ltf?.fvgs || [];
  const bsl = analysis?.ltf?.bsl || [];
  const ssl = analysis?.ltf?.ssl || [];
  const statusColor = analysis?.signal === 'NO TRADE' ? 'text-amber-300' : analysis?.signal ? 'text-emerald-300' : 'text-slate-400';

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-3xl mx-auto">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-black text-white font-mono">{selectedIndex} SMC PRO</span>
              <span className={`text-xs font-mono ${marketFresh ? 'text-emerald-300' : 'text-amber-300'}`}>{marketFresh ? `₹${fmt(currentMarket?.ltp)}` : 'SPOT —'}</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">BOS • CHoCH • FVG • Order Blocks • BSL/SSL • Multi-timeframe</div>
          </div>
          <button onClick={runAnalysis} disabled={loading} className="px-3 py-2 rounded-lg bg-cyan-500 text-[#070B12] text-[10px] font-black flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />{loading ? 'ANALYZING' : 'REFRESH'}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">LOWER TIMEFRAME</label>
            <select value={timeframe} onChange={e => setTimeframe(e.target.value as typeof timeframe)} className="w-full p-2 rounded-lg bg-[#070B12] border border-[#1C2740] text-white text-xs">
              <option value="ONE_MINUTE">1 minute</option>
              <option value="FIVE_MINUTE">5 minutes</option>
              <option value="FIFTEEN_MINUTE">15 minutes</option>
              <option value="ONE_HOUR">1 hour</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">SMC PROFILE</label>
            <select value={strategy} onChange={e => setStrategy(e.target.value as typeof strategy)} className="w-full p-2 rounded-lg bg-[#070B12] border border-[#1C2740] text-white text-xs">
              <option value="Guardeer">Guardeer</option>
              <option value="Inner Circle">Inner Circle ICT</option>
            </select>
          </div>
        </div>
        <div className="text-[10px] text-slate-400">Daily HTF + hourly MTF + selected LTF • data source: Angel One historical candles • fetched {timeText(lastUpdated)}</div>
      </div>

      {error && <div className="card-base p-3 border border-rose-500/40 bg-rose-500/5 flex items-start gap-2 text-xs text-rose-200"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" /><span>{error}</span></div>}

      {loading && <div className="card-base p-4 border border-[#1C2740] bg-[#101726] text-xs text-slate-300">Fetching real HTF/MTF/LTF candles and calculating SMC structure…</div>}

      <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
        {[['HTF 1D', htfCandles.length], ['MTF 1H', mtfCandles.length], [`LTF ${timeframe.replace('_MINUTE', 'm').replace('ONE_HOUR', '1h')}`, ltfCandles.length]].map(([label, count]) => (
          <div key={String(label)} className="p-3 rounded-xl bg-[#101726] border border-[#1C2740]">
            <div className="text-slate-500">{label}</div><div className="text-white font-black text-sm mt-1">{count} candles</div>
          </div>
        ))}
      </div>

      {analysis && (
        <>
          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div><div className="text-[10px] text-slate-500">STRUCTURE RESULT</div><div className={`text-lg font-black mt-1 ${statusColor}`}>{analysis.signal || 'NO TRADE'}</div></div>
              <div className="text-right"><div className="text-[10px] text-slate-500">HTF BIAS</div><div className="text-sm font-black text-white mt-1">{analysis.bias || 'UNKNOWN'}</div></div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="p-2 rounded-lg bg-[#070B12]"><div className="text-[9px] text-slate-500">ENTRY</div><div className="text-white font-bold mt-1">{fmt(analysis.entry)}</div></div>
              <div className="p-2 rounded-lg bg-[#070B12]"><div className="text-[9px] text-slate-500">STOP LOSS</div><div className="text-white font-bold mt-1">{fmt(analysis.stop_loss)}</div></div>
              <div className="p-2 rounded-lg bg-[#070B12]"><div className="text-[9px] text-slate-500">HTF BOS</div><div className="text-white font-bold mt-1">{analysis.htf?.bos ? 'YES' : 'NO'}</div></div>
              <div className="p-2 rounded-lg bg-[#070B12]"><div className="text-[9px] text-slate-500">MTF CHoCH</div><div className="text-white font-bold mt-1">{analysis.mtf?.choch ? 'YES' : 'NO'}</div></div>
            </div>
            <div className="text-[10px] text-slate-400">{analysis.note || 'Advisory only.'} Execution allowed: {analysis.execution_allowed ? 'YES' : 'NO — blocked'}</div>
            {analysis.reasons?.length ? <ul className="list-disc pl-5 space-y-1 text-[11px] text-amber-200">{analysis.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul> : null}
          </div>

          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-white"><BarChart2 className="w-4 h-4 text-cyan-400" />REAL OHLC CANDLE VIEW (LAST {chartCandles.length})</div>
            {chartCandles.length ? (
              <div className="relative h-40 flex items-stretch gap-1 border-b border-[#1C2740] bg-[#070B12] rounded-lg p-2">
                {chartCandles.map((candle, index) => {
                  const wickTop = ((chartBounds.max - candle.high) / chartBounds.range) * 100;
                  const wickHeight = Math.max(1, ((candle.high - candle.low) / chartBounds.range) * 100);
                  const bodyTop = ((chartBounds.max - Math.max(candle.open, candle.close)) / chartBounds.range) * 100;
                  const bodyHeight = Math.max(1.5, (Math.abs(candle.close - candle.open) / chartBounds.range) * 100);
                  const bullish = candle.close >= candle.open;
                  return (
                    <div key={`${candle.timestamp}-${index}`} className="relative flex-1 min-w-0">
                      <div className={`absolute left-1/2 -translate-x-1/2 w-px ${bullish ? 'bg-emerald-400' : 'bg-rose-400'}`} style={{ top: `${wickTop}%`, height: `${wickHeight}%` }} />
                      <div className={`absolute left-[20%] right-[20%] min-h-[2px] ${bullish ? 'bg-emerald-400' : 'bg-rose-400'}`} style={{ top: `${bodyTop}%`, height: `${bodyHeight}%` }} title={`${candle.timestamp} O ${candle.open} H ${candle.high} L ${candle.low} C ${candle.close}`} />
                    </div>
                  );
                })}
              </div>
            ) : <p className="text-xs text-slate-400">No verified candle rows available.</p>}
            <div className="text-[10px] text-slate-400">Historical candle chart only. No live candles are fabricated and no order is authorized from this analysis.</div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
              <div className="text-xs font-bold text-white">ORDER BLOCKS ({orderBlocks.length})</div>
              {orderBlocks.length ? orderBlocks.slice(-6).reverse().map((zone, i) => <div key={i} className="p-2 rounded-lg bg-[#070B12] text-[11px] text-slate-300">{zone.type?.toUpperCase()} • {fmt(zone.bottom)} — {fmt(zone.top)}</div>) : <div className="text-xs text-slate-400">No confirmed order blocks in returned candles.</div>}
            </div>
            <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
              <div className="text-xs font-bold text-white">FAIR VALUE GAPS ({fvgs.length})</div>
              {fvgs.length ? fvgs.slice(-6).reverse().map((zone, i) => <div key={i} className="p-2 rounded-lg bg-[#070B12] text-[11px] text-slate-300">{zone.type?.toUpperCase()} • {fmt(zone.bottom)} — {fmt(zone.top)}</div>) : <div className="text-xs text-slate-400">No confirmed FVG in returned candles.</div>}
            </div>
          </div>

          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
            <div className="text-xs font-bold text-white">LIQUIDITY MAP</div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-3 rounded-lg bg-[#070B12]"><div className="text-[10px] text-slate-500">BUY-SIDE LIQUIDITY (BSL)</div><div className="text-emerald-300 font-bold mt-1">{bsl.length ? bsl.map(fmt).join(' • ') : 'Not detected'}</div></div>
              <div className="p-3 rounded-lg bg-[#070B12]"><div className="text-[10px] text-slate-500">SELL-SIDE LIQUIDITY (SSL)</div><div className="text-rose-300 font-bold mt-1">{ssl.length ? ssl.map(fmt).join(' • ') : 'Not detected'}</div></div>
            </div>
            {analysis.ltf?.poi && <div className="text-xs text-cyan-300">Point of Interest: {analysis.ltf.poi.type?.toUpperCase()} • {fmt(analysis.ltf.poi.bottom)} — {fmt(analysis.ltf.poi.top)}</div>}
          </div>
        </>
      )}

      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] flex items-start gap-3">
        <Shield className="w-5 h-5 text-cyan-400 shrink-0" />
        <div className="space-y-1"><div className="text-xs font-black text-white">SMC safety gate</div><div className="text-[11px] text-slate-400">Source: Angel One historical candles • Daily HTF / Hourly MTF / selected LTF • {analysis?.execution_allowed ? 'Execution permitted by analyzer' : 'Advisory only; execution blocked'}.</div></div>
      </div>
    </div>
  );
};
