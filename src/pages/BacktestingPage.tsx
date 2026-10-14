import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService } from '../services/api';
import { History, AlertTriangle, Play, RefreshCw } from 'lucide-react';

type BacktestTrade = {
  side?: string;
  entry_time?: string;
  exit_time?: string;
  entry_price?: number;
  exit_price?: number;
  stop_loss?: number;
  target?: number;
  net_r?: number;
  pnl?: number;
  exit_reason?: string;
};
type BacktestReport = {
  status?: string;
  mode?: string;
  candle_count?: number;
  first_candle?: string;
  last_candle?: string;
  metrics?: Record<string, number | null>;
  trades?: BacktestTrade[];
  assumptions?: string[];
};

const localDate = (date: Date) => {
  const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return adjusted.toISOString().slice(0, 10);
};

export const BacktestingPage: React.FC = () => {
  const { selectedIndex } = useTrading();
  const [interval, setInterval] = useState('FIVE_MINUTE');
  const [fromDate, setFromDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 7);
    return localDate(date);
  });
  const [toDate, setToDate] = useState(() => localDate(new Date()));
  const [fastEma, setFastEma] = useState(8);
  const [slowEma, setSlowEma] = useState(13);
  const [stopAtr, setStopAtr] = useState(1.5);
  const [targetR, setTargetR] = useState(2);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<BacktestReport | null>(null);

  const handleRunBacktest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (new Date(toDate) <= new Date(fromDate)) {
      setError('End date must be after start date.');
      return;
    }
    if (fastEma >= slowEma) {
      setError('Fast EMA must be smaller than Slow EMA.');
      return;
    }
    const rangeDays = (Date.parse(toDate) - Date.parse(fromDate)) / 86400000;
    if (rangeDays > 31) {
      setError('Historical backtest range is limited to 31 days per request.');
      return;
    }

    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const response = await fetch(`${apiService.getSignalBackend().replace(/\/+$/, '')}/v1/backtest/historical`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Device-Id': apiService.getDeviceId(),
        },
        body: JSON.stringify({
          index: selectedIndex,
          interval,
          from_date: fromDate,
          to_date: toDate,
          fast_ema: fastEma,
          slow_ema: slowEma,
          atr_period: 14,
          stop_atr: stopAtr,
          target_r: targetR,
          max_hold_bars: 30,
          slippage_r: 0.02,
          transaction_cost_r: 0.02,
          initial_capital: 100000,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = typeof body?.detail === 'string'
          ? body.detail
          : (body?.detail?.message || JSON.stringify(body?.detail || body));
        throw new Error(detail || `Backtest failed with HTTP ${response.status}`);
      }
      if (!body?.report || !Array.isArray(body.report.trades) || typeof body.report.metrics !== 'object') {
        throw new Error('Backend response did not contain a validated historical backtest report.');
      }
      setReport(body.report as BacktestReport);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Historical backtest request failed');
    } finally {
      setLoading(false);
    }
  };

  const metrics = report?.metrics || {};
  const metric = (key: string, suffix = '') => {
    const value = metrics[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    return `${value.toLocaleString('en-IN', { maximumFractionDigits: 3 })}${suffix}`;
  };

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-3xl mx-auto font-mono">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="text-sm font-black text-white uppercase">HISTORICAL BACKTEST</div>
          <div className="text-xs text-slate-400 mt-0.5">Angel One candles • EMA/ATR • fees and slippage • no synthetic metrics</div>
        </div>
        <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400"><History className="w-5 h-5" /></div>
      </div>

      <form onSubmit={handleRunBacktest} className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3 text-xs">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-slate-400 block mb-1">Instrument</label>
            <div className="p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white font-bold">{selectedIndex}</div>
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Candle interval</label>
            <select value={interval} onChange={e => setInterval(e.target.value)} className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white">
              <option value="ONE_MINUTE">1 minute</option>
              <option value="FIVE_MINUTE">5 minutes</option>
              <option value="FIFTEEN_MINUTE">15 minutes</option>
              <option value="ONE_HOUR">1 hour</option>
            </select>
          </div>
          <div>
            <label className="text-slate-400 block mb-1">From date</label>
            <input type="date" value={fromDate} max={toDate} onChange={e => setFromDate(e.target.value)} required className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white" />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">To date</label>
            <input type="date" value={toDate} min={fromDate} max={localDate(new Date())} onChange={e => setToDate(e.target.value)} required className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white" />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Fast EMA (2–100)</label>
            <input type="number" min={2} max={100} value={fastEma} onChange={e => setFastEma(Math.max(2, Math.min(100, Number(e.target.value) || 8)))} className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white" />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Slow EMA (3–200)</label>
            <input type="number" min={3} max={200} value={slowEma} onChange={e => setSlowEma(Math.max(3, Math.min(200, Number(e.target.value) || 13)))} className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white" />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Stop ATR multiple</label>
            <input type="number" min={0.1} max={10} step={0.1} value={stopAtr} onChange={e => setStopAtr(Math.max(0.1, Math.min(10, Number(e.target.value) || 1.5)))} className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white" />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Target (R multiple)</label>
            <input type="number" min={0.1} max={20} step={0.1} value={targetR} onChange={e => setTargetR(Math.max(0.1, Math.min(20, Number(e.target.value) || 2)))} className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white" />
          </div>
        </div>
        <button type="submit" disabled={loading} className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#070B12] font-black text-xs flex items-center justify-center space-x-2 disabled:opacity-50">
          {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          <span>{loading ? 'FETCHING HISTORICAL CANDLES…' : 'RUN REAL HISTORICAL BACKTEST'}</span>
        </button>
        <p className="text-[10px] text-slate-400">Requires an authenticated Angel One session and enough real historical candles. Maximum 31 days. This is a long-only underlying-index research baseline, not an options-premium backtest.</p>
      </form>

      {error && (
        <div className="card-base p-3 border border-rose-500/40 bg-rose-500/5 flex items-start gap-2 text-xs text-rose-200">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {report && (
        <>
          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
            <div className="flex items-center justify-between gap-3">
              <div className="text-xs font-bold text-white">RESULT • {report.status || 'UNKNOWN'}</div>
              <div className="text-[10px] text-cyan-300">{report.candle_count ?? 0} verified candles</div>
            </div>
            <div className="text-[10px] text-slate-400">{report.mode || 'Historical engine'} • {report.first_candle || fromDate} → {report.last_candle || toDate}</div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                ['Trades', metric('n')],
                ['Win rate', metric('win_rate', '%') === '—' ? '—' : `${((metrics.win_rate as number) * 100).toFixed(1)}%`],
                ['Expectancy (R)', metric('expectancy_r')],
                ['Profit factor', metric('profit_factor')],
                ['Net total (R)', metric('net_total_r')],
                ['Max drawdown (R)', metric('max_drawdown_r')],
                ['Ending equity', metric('ending_equity')],
                ['Return', metric('return_pct', '%')],
              ].map(([label, value]) => (
                <div key={label} className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740]">
                  <div className="text-[10px] text-slate-500">{label}</div>
                  <div className="text-sm text-white font-black mt-1">{value}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3">
            <div className="text-xs font-bold text-white">TRADE LEDGER ({report.trades?.length || 0})</div>
            {(report.trades || []).length === 0 ? <p className="text-xs text-slate-400">No trades were produced by the historical strategy for this date range.</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-[10px] text-left">
                  <thead><tr className="text-slate-500 border-b border-[#1C2740]"><th className="p-2">Entry</th><th className="p-2">Exit</th><th className="p-2">Side</th><th className="p-2">Net R</th><th className="p-2">P&amp;L</th><th className="p-2">Reason</th></tr></thead>
                  <tbody>{(report.trades || []).slice(-20).reverse().map((trade, index) => (
                    <tr key={`${trade.entry_time || 'entry'}-${index}`} className="border-b border-[#1C2740]/60 text-slate-300">
                      <td className="p-2 whitespace-nowrap">{trade.entry_time || '—'}<br />{trade.entry_price ?? '—'}</td>
                      <td className="p-2 whitespace-nowrap">{trade.exit_time || '—'}<br />{trade.exit_price ?? '—'}</td>
                      <td className="p-2">{trade.side || 'LONG'}</td>
                      <td className={`p-2 font-bold ${(trade.net_r || 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{trade.net_r ?? '—'}</td>
                      <td className="p-2">{typeof trade.pnl === 'number' ? trade.pnl.toLocaleString('en-IN') : '—'}</td>
                      <td className="p-2">{trade.exit_reason || '—'}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </div>
          <div className="card-base p-4 border border-[#1C2740] bg-[#101726]">
            <div className="text-xs font-bold text-white mb-2">BACKTEST ASSUMPTIONS</div>
            <ul className="list-disc pl-5 space-y-1 text-[10px] text-slate-400">{(report.assumptions || []).map((item, index) => <li key={index}>{item}</li>)}</ul>
          </div>
        </>
      )}
    </div>
  );
};
