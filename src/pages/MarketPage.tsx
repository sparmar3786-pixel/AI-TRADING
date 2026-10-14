import React from 'react';
import { useTrading } from '../context/TradingContext';
import { INDEX_CONFIG } from '../services/api';
import { TrendingUp, TrendingDown, Activity, Gauge, ShieldAlert, AlertTriangle } from 'lucide-react';

export const MarketPage: React.FC = () => {
  const { selectedIndex, market } = useTrading();
  const currentMarket = market[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];
  const ageMs = currentMarket?.timestamp ? Date.now() - Date.parse(currentMarket.timestamp) : Number.POSITIVE_INFINITY;
  const isLive = Boolean(currentMarket?.live === true && Number.isFinite(ageMs) && ageMs >= 0 && ageMs <= 120000);
  const ltp = isLive ? currentMarket?.ltp : null;
  const change = isLive ? currentMarket?.change : null;
  const changePercent = isLive ? currentMarket?.change_percent : null;
  const isPositive = typeof change === 'number' && change >= 0;
  const fmt = (value?: number | null) => isLive && typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—';

  return (
    <div className="p-3 pb-8 space-y-3.5 select-none max-w-2xl mx-auto">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D]">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-black text-cyan-400 font-mono tracking-wider">{selectedIndex} SPOT</div>
            <div className="text-3xl font-black text-white font-mono mt-1">{ltp != null ? `₹${fmt(ltp)}` : 'PRICE UNAVAILABLE'}</div>
            <div className={`text-[10px] mt-1 font-mono ${isLive ? 'text-emerald-300' : 'text-rose-300'}`}>{isLive ? `LIVE • snapshot age ${Math.round(ageMs / 1000)}s` : 'STALE / UNKNOWN — NOT A LIVE QUOTE'}</div>
          </div>
          <div className="text-right">
            {isLive && typeof change === 'number' && typeof changePercent === 'number' ? (
              <div className={`inline-flex items-center space-x-1 px-2.5 py-1 rounded-xl text-xs font-bold font-mono ${isPositive ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'}`}>
                {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                <span>{isPositive ? '+' : ''}{change.toFixed(2)} ({isPositive ? '+' : ''}{changePercent.toFixed(2)}%)</span>
              </div>
            ) : <span className="text-xs text-slate-500">Change —</span>}
            <div className="text-[11px] text-slate-400 mt-1 font-mono">Lot Size: <strong className="text-white">{cfg.lotSize}</strong></div>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-2 pt-3 mt-3 border-t border-[#1C2740] text-center font-mono">
          {([['Open', currentMarket?.open], ['High', currentMarket?.high], ['Low', currentMarket?.low], ['VWAP', currentMarket?.vwap]] as const).map(([label, value]) => (
            <div key={label} className="p-2 rounded-xl bg-[#0E1524]">
              <div className="text-[9px] text-slate-400 uppercase">{label}</div>
              <div className="text-xs font-bold text-slate-200 mt-0.5">{fmt(value)}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card-base p-4 border border-amber-500/40 bg-amber-500/5 space-y-2">
        <div className="flex items-center gap-2 text-amber-300 text-xs font-bold"><AlertTriangle className="w-4 h-4" />CANDLE HISTORY NOT CONNECTED</div>
        <p className="text-xs text-slate-300 leading-relaxed">RSI, EMA, ATR, Supertrend, VWAP and volume structure require a validated OHLC candle series. The current frontend previously calculated indicators from one price and displayed fixed sample volume bars; those unverified values are now withheld.</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726]">
          <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1"><Gauge className="w-4 h-4 text-cyan-400" /><span className="font-semibold">RSI / EMA / ATR</span></div>
          <div className="text-lg font-black text-slate-300 font-mono mt-1">NOT CALCULATED</div>
          <div className="text-[10px] text-slate-400 mt-1">Waiting for real candles</div>
        </div>
        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726]">
          <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1"><Activity className="w-4 h-4 text-cyan-400" /><span className="font-semibold">Trend / Volume</span></div>
          <div className="text-lg font-black text-slate-300 font-mono mt-1">UNKNOWN</div>
          <div className="text-[10px] text-slate-400 mt-1">No fabricated direction</div>
        </div>
      </div>

      <div className="card-base p-4 border border-[#1C2740] bg-[#0E1524] space-y-2.5">
        <div className="text-xs font-black text-slate-400 uppercase tracking-wider font-mono flex items-center gap-2"><ShieldAlert className="w-4 h-4" />Indicator safety</div>
        <div className="text-xs text-slate-300">No technical signal is inferred from a base-price placeholder. Connect timestamped historical candles before using indicator values in a trade decision.</div>
      </div>
    </div>
  );
};
