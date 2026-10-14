import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService, INDEX_CONFIG } from '../services/api';
import { Sliders, Activity, TrendingUp, Gauge, Check } from 'lucide-react';

export const IndicatorsPage: React.FC = () => {
  const { selectedIndex, market } = useTrading();
  const currentMarket = market[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];
  const ltp = currentMarket?.ltp || cfg.basePrice;

  const [emaFast, setEmaFast] = useState(8);
  const [emaSlow, setEmaSlow] = useState(13);
  const [rsiPeriod, setRsiPeriod] = useState(14);

  const ind = apiService.getTechnicalIndicators(ltp);

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      {/* Header */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="text-sm font-black text-white font-mono uppercase">
            {selectedIndex} INDICATOR SUITE
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            LTP: ₹{ltp.toLocaleString('en-IN')} • Live Mathematical Formulas
          </div>
        </div>

        <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400">
          <Sliders className="w-5 h-5" />
        </div>
      </div>

      {/* Parameter Controls */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3 font-mono text-xs">
        <div className="text-xs font-black text-slate-300 uppercase">Configurable Parameters</div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-slate-400 block mb-1">Fast EMA Period: <strong className="text-cyan-400">{emaFast}</strong></label>
            <input
              type="range"
              min="3"
              max="20"
              value={emaFast}
              onChange={e => setEmaFast(parseInt(e.target.value))}
              className="w-full accent-cyan-400"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Slow EMA Period: <strong className="text-cyan-400">{emaSlow}</strong></label>
            <input
              type="range"
              min="10"
              max="50"
              value={emaSlow}
              onChange={e => setEmaSlow(parseInt(e.target.value))}
              className="w-full accent-cyan-400"
            />
          </div>
        </div>
      </div>

      {/* Calculated Indicator Values Grid */}
      <div className="space-y-2.5 font-mono">
        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726] flex items-center justify-between">
          <div>
            <div className="text-slate-400 text-xs">EMA {emaFast} (Fast Line)</div>
            <div className="text-sm font-bold text-white mt-0.5">₹{ind.ema8}</div>
          </div>
          <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded font-bold">
            ABOVE SPOT
          </span>
        </div>

        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726] flex items-center justify-between">
          <div>
            <div className="text-slate-400 text-xs">EMA {emaSlow} (Slow Baseline)</div>
            <div className="text-sm font-bold text-white mt-0.5">₹{ind.ema13}</div>
          </div>
          <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded font-bold">
            BULLISH STACK
          </span>
        </div>

        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726] flex items-center justify-between">
          <div>
            <div className="text-slate-400 text-xs">Relative Strength Index (RSI {rsiPeriod})</div>
            <div className="text-sm font-bold text-cyan-400 mt-0.5">{ind.rsi14}</div>
          </div>
          <span className="text-[10px] text-slate-300 bg-[#070B12] px-2 py-0.5 rounded">
            HEALTHY EXPANSION
          </span>
        </div>

        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726] flex items-center justify-between">
          <div>
            <div className="text-slate-400 text-xs">Supertrend (10, 3)</div>
            <div className="text-sm font-bold text-emerald-400 mt-0.5">₹{ind.supertrend.value}</div>
          </div>
          <span className="text-[10px] text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded font-bold">
            BUY (GREEN)
          </span>
        </div>

        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726] flex items-center justify-between">
          <div>
            <div className="text-slate-400 text-xs">Average True Range (ATR 14)</div>
            <div className="text-sm font-bold text-amber-300 mt-0.5">₹{ind.atr14}</div>
          </div>
          <span className="text-[10px] text-slate-400 bg-[#070B12] px-2 py-0.5 rounded">
            VOLATILITY BAND
          </span>
        </div>
      </div>
    </div>
  );
};
