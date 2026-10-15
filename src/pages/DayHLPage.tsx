import React, { useMemo } from 'react';
import { useTrading } from '../context/TradingContext';

const fmt = (v?: number) => typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—';

export const DayHLPage: React.FC = () => {
  const { selectedIndex, market, lastUpdated, isLive, refresh, isRefreshing } = useTrading();
  const row = market[selectedIndex];
  const levels = useMemo(() => {
    if (!row) return null;
    const high = Number(row.session_high ?? row.high);
    const low = Number(row.session_low ?? row.low);
    const prevClose = Number(row.close);
    if (![high, low, prevClose].every(Number.isFinite) || high <= 0 || low <= 0 || high < low) return null;
    return { high, low, prevClose, range: high - low, midpoint: (high + low) / 2 };
  }, [row]);

  return <section className="mx-auto w-full max-w-5xl p-4 sm:p-6 space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="text-xs font-bold tracking-[0.2em] text-cyan-400">PRICE LEVELS</p><h1 className="mt-1 text-2xl font-black text-white">DAY HL</h1><p className="mt-1 text-sm text-slate-400">Session High / Low • {selectedIndex}</p></div>
      <button onClick={() => void refresh()} disabled={isRefreshing} className="rounded-xl border border-cyan-500/40 px-4 py-2 text-sm font-bold text-cyan-300 disabled:opacity-50">{isRefreshing ? 'Refreshing…' : 'Refresh data'}</button>
    </header>
    <div className="flex items-center gap-2 text-xs"><span className={`h-2 w-2 rounded-full ${isLive ? 'bg-emerald-400' : 'bg-rose-400'}`}/><span className={isLive ? 'text-emerald-300' : 'text-rose-300'}>{isLive ? 'Feed reports live' : 'Feed not live'}</span><span className="text-slate-500">• Updated {lastUpdated || 'not yet'}</span></div>
    {!levels ? <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5 text-sm text-amber-200">Valid DAY HL values are unavailable. Refresh the feed and verify live-data freshness before using these levels.</div> : <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5"><div className="text-xs font-bold tracking-widest text-emerald-300">DAY HIGH</div><div className="mt-2 text-3xl font-black text-white">{fmt(levels.high)}</div><div className="mt-1 text-xs text-slate-400">Session high</div></div>
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/5 p-5"><div className="text-xs font-bold tracking-widest text-rose-300">DAY LOW</div><div className="mt-2 text-3xl font-black text-white">{fmt(levels.low)}</div><div className="mt-1 text-xs text-slate-400">Session low</div></div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-4"><div className="text-xs text-slate-400">Range</div><div className="mt-1 text-xl font-bold text-white">{fmt(levels.range)}</div></div>
        <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-4"><div className="text-xs text-slate-400">High / Low Midpoint</div><div className="mt-1 text-xl font-bold text-white">{fmt(levels.midpoint)}</div></div>
        <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-4"><div className="text-xs text-slate-400">Feed close field</div><div className="mt-1 text-xl font-bold text-white">{fmt(levels.prevClose)}</div><div className="mt-1 text-[11px] text-slate-500">Verify whether upstream maps this to previous close.</div></div>
      </div>
    </>}
    <p className="text-xs leading-5 text-slate-500">DAY HL displays spot/index levels only. Values are sourced from the existing market feed; this page does not create buy/sell signals or infer option premiums. Confirm session timestamps and tick freshness in Data Health.</p>
  </section>;
};
