import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { INDEX_CONFIG } from '../services/api';
import { AlertTriangle, Shield, BarChart2 } from 'lucide-react';

export const SmcChartPage: React.FC = () => {
  const { selectedIndex, market } = useTrading();
  const currentMarket = market[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];
  const ageMs = currentMarket?.timestamp ? Date.now() - Date.parse(currentMarket.timestamp) : Number.POSITIVE_INFINITY;
  const marketFresh = Boolean(currentMarket?.live === true && Number.isFinite(ageMs) && ageMs >= 0 && ageMs <= 120000);
  const [timeframe, setTimeframe] = useState<'1m' | '3m' | '5m' | '15m'>('5m');

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-3xl mx-auto">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-sm font-black text-white font-mono">{selectedIndex} SMC PRO</span>
            <span className="text-xs text-cyan-400 font-mono">{marketFresh ? `₹${currentMarket.ltp.toLocaleString('en-IN')}` : 'LTP —'}</span>
          </div>
          <div className="text-[10px] text-slate-400 font-medium mt-0.5">BOS • CHoCH • FVG • Order Blocks • Liquidity</div>
        </div>
        <div className="flex items-center space-x-1 bg-[#070B12] p-1 rounded-xl border border-[#1C2740]">
          {(['1m', '3m', '5m', '15m'] as const).map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)} className={`px-2.5 py-1 text-xs font-bold rounded-lg font-mono transition-all ${timeframe === tf ? 'bg-cyan-500 text-[#070B12]' : 'text-slate-400 hover:text-white'}`}>{tf}</button>
          ))}
        </div>
      </div>

      <div className="card-base p-4 border border-amber-500/40 bg-amber-500/5 space-y-3">
        <div className="flex items-center gap-2 text-amber-300 font-bold text-xs">
          <AlertTriangle className="w-4 h-4" />
          <span>SMC ANALYSIS UNAVAILABLE — NO VERIFIED CANDLES</span>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">
          The current frontend does not fetch timestamped OHLC candles for {selectedIndex} at the selected {timeframe} timeframe. It previously drew sample candles and hardcoded bullish BOS/CHoCH, order blocks and liquidity levels. Those fabricated levels are now withheld.
        </p>
        <div className="grid grid-cols-2 gap-3 text-xs font-mono">
          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-[10px] text-slate-500">MARKET PRICE</div>
            <div className={marketFresh ? 'text-emerald-400 font-bold mt-1' : 'text-rose-400 font-bold mt-1'}>{marketFresh ? `₹${currentMarket.ltp.toLocaleString('en-IN')}` : 'Unavailable / stale'}</div>
          </div>
          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-[10px] text-slate-500">CANDLE SOURCE</div>
            <div className="text-rose-400 font-bold mt-1">Not connected</div>
          </div>
        </div>
        <div className="text-[11px] text-slate-400 leading-relaxed">
          Required next step: connect an authenticated historical/live candle endpoint, validate exchange timestamps and candle ordering, then calculate BOS/CHoCH/FVG/OB from the real OHLC series. No trade setup should be inferred from this screen until that succeeds.
        </div>
      </div>

      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] flex items-start gap-3">
        <BarChart2 className="w-5 h-5 text-cyan-400 shrink-0" />
        <div className="space-y-1">
          <div className="text-xs font-black text-white">SMC chart safety gate</div>
          <div className="text-[11px] text-slate-400">Instrument: {cfg.name} • Timeframe: {timeframe} • Candle validation: NOT PASSED</div>
          <div className="text-[11px] text-slate-400">Signal use: blocked until real candles and data freshness are verified.</div>
        </div>
        <Shield className="w-4 h-4 text-amber-300 shrink-0" />
      </div>
    </div>
  );
};
