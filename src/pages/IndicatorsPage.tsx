import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { INDEX_CONFIG } from '../services/api';
import { Sliders, AlertTriangle } from 'lucide-react';

export const IndicatorsPage: React.FC = () => {
  const { selectedIndex, market } = useTrading();
  const currentMarket = market[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];
  const ageMs = currentMarket?.timestamp ? Date.now() - Date.parse(currentMarket.timestamp) : Number.POSITIVE_INFINITY;
  const isLive = Boolean(currentMarket?.live === true && Number.isFinite(ageMs) && ageMs >= 0 && ageMs <= 120000);

  const [emaFast, setEmaFast] = useState(8);
  const [emaSlow, setEmaSlow] = useState(13);
  const [rsiPeriod, setRsiPeriod] = useState(14);

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="text-sm font-black text-white font-mono uppercase">{selectedIndex} INDICATOR SUITE</div>
          <div className={`text-xs mt-0.5 ${isLive ? 'text-emerald-300' : 'text-rose-300'}`}>{isLive ? `LTP: ₹${currentMarket?.ltp?.toLocaleString('en-IN')}` : 'LTP: unavailable / stale'} • Candle data: {isLive ? 'quote live, candles still required' : 'not verified'}</div>
        </div>
        <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400"><Sliders className="w-5 h-5" /></div>
      </div>

      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3 font-mono text-xs">
        <div className="text-xs font-black text-slate-300 uppercase">Requested Parameters</div>
        <div className="grid grid-cols-3 gap-3">
          <div><label className="text-slate-400 block mb-1">Fast EMA: {emaFast}</label><input type="range" min="3" max="20" value={emaFast} onChange={e => setEmaFast(parseInt(e.target.value, 10))} className="w-full accent-cyan-400" /></div>
          <div><label className="text-slate-400 block mb-1">Slow EMA: {emaSlow}</label><input type="range" min="10" max="50" value={emaSlow} onChange={e => setEmaSlow(parseInt(e.target.value, 10))} className="w-full accent-cyan-400" /></div>
          <div><label className="text-slate-400 block mb-1">RSI period: {rsiPeriod}</label><input type="range" min="5" max="30" value={rsiPeriod} onChange={e => setRsiPeriod(parseInt(e.target.value, 10))} className="w-full accent-cyan-400" /></div>
        </div>
      </div>

      <div className="card-base p-4 border border-amber-500/40 bg-amber-500/5 space-y-2">
        <div className="flex items-center gap-2 text-amber-300 text-xs font-bold"><AlertTriangle className="w-4 h-4" />INDICATOR VALUES WITHHELD</div>
        <p className="text-xs text-slate-300 leading-relaxed">The current frontend has no validated OHLC candle-series endpoint wired into this page. Calculating RSI/EMA/ATR/Supertrend from one LTP would be mathematically misleading, so the page will not invent values or bullish/bearish labels.</p>
        <p className="text-[11px] text-slate-400">Instrument: {cfg.name} • Parameters selected: EMA {emaFast}/{emaSlow}, RSI {rsiPeriod}. Values remain unavailable until real candle history is connected.</p>
      </div>
    </div>
  );
};
