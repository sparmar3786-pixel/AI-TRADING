import React from 'react';
import { useTrading } from '../context/TradingContext';
import { INDEX_CONFIG, apiService } from '../services/api';
import { TrendingUp, TrendingDown, Activity, BarChart2, Gauge, Shield } from 'lucide-react';

export const MarketPage: React.FC = () => {
  const { selectedIndex, market } = useTrading();
  const currentMarket = market[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];

  const ltp = currentMarket ? currentMarket.ltp : cfg.basePrice;
  const change = currentMarket ? currentMarket.change : 0;
  const changePercent = currentMarket ? currentMarket.change_percent : 0;
  const isPositive = change >= 0;

  const indicators = apiService.getTechnicalIndicators(ltp);

  return (
    <div className="p-3 pb-8 space-y-3.5 select-none max-w-2xl mx-auto">
      {/* Header Price Block */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-black text-cyan-400 font-mono tracking-wider">
              {selectedIndex} SPOT
            </div>
            <div className="text-3xl font-black text-white font-mono mt-1">
              ₹{ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>

          <div className="text-right">
            <div
              className={`inline-flex items-center space-x-1 px-2.5 py-1 rounded-xl text-xs font-bold font-mono ${
                isPositive ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
              }`}
            >
              {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
              <span>{isPositive ? '+' : ''}{change.toFixed(2)} ({isPositive ? '+' : ''}{changePercent.toFixed(2)}%)</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1 font-mono">
              Lot Size: <strong className="text-white">{cfg.lotSize}</strong>
            </div>
          </div>
        </div>

        {/* OHLC Grid */}
        <div className="grid grid-cols-4 gap-2 pt-3 mt-3 border-t border-[#1C2740] text-center font-mono">
          <div className="p-2 rounded-xl bg-[#0E1524]">
            <div className="text-[9px] text-slate-400 uppercase">Open</div>
            <div className="text-xs font-bold text-slate-200 mt-0.5">
              ₹{currentMarket?.open.toLocaleString('en-IN')}
            </div>
          </div>
          <div className="p-2 rounded-xl bg-[#0E1524]">
            <div className="text-[9px] text-emerald-400 uppercase">High</div>
            <div className="text-xs font-bold text-emerald-300 mt-0.5">
              ₹{currentMarket?.high.toLocaleString('en-IN')}
            </div>
          </div>
          <div className="p-2 rounded-xl bg-[#0E1524]">
            <div className="text-[9px] text-rose-400 uppercase">Low</div>
            <div className="text-xs font-bold text-rose-300 mt-0.5">
              ₹{currentMarket?.low.toLocaleString('en-IN')}
            </div>
          </div>
          <div className="p-2 rounded-xl bg-[#0E1524]">
            <div className="text-[9px] text-cyan-400 uppercase">VWAP</div>
            <div className="text-xs font-bold text-cyan-300 mt-0.5">
              ₹{currentMarket?.vwap.toLocaleString('en-IN')}
            </div>
          </div>
        </div>
      </div>

      {/* Market Breadth & Sentiment Meters */}
      <div className="grid grid-cols-2 gap-3">
        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726]">
          <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1">
            <Gauge className="w-4 h-4 text-cyan-400" />
            <span className="font-semibold">RSI (14) Momentum</span>
          </div>
          <div className="text-2xl font-black text-white font-mono mt-1">
            {indicators.rsi14}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">
            {indicators.rsi14 > 70 ? 'Overbought (>70)' : indicators.rsi14 < 30 ? 'Oversold (<30)' : 'Neutral Bullish (50-70)'}
          </div>
        </div>

        <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726]">
          <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1">
            <Activity className="w-4 h-4 text-emerald-400" />
            <span className="font-semibold">Supertrend (10, 3)</span>
          </div>
          <div className="text-sm font-black text-emerald-400 font-mono mt-1 flex items-center space-x-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>{indicators.supertrend.direction}</span>
          </div>
          <div className="text-[10px] text-slate-400 mt-1 font-mono">
            Support: ₹{indicators.supertrend.value.toLocaleString('en-IN')}
          </div>
        </div>
      </div>

      {/* Moving Averages Stack */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#0E1524] space-y-2.5">
        <div className="text-xs font-black text-slate-400 uppercase tracking-wider font-mono">
          Exponential Moving Averages Stack
        </div>
        <div className="grid grid-cols-2 gap-2 font-mono text-xs">
          <div className="p-2.5 rounded-xl bg-[#121A2D] flex justify-between items-center">
            <span className="text-slate-400">EMA 8 (Fast)</span>
            <span className="font-bold text-white">₹{indicators.ema8}</span>
          </div>
          <div className="p-2.5 rounded-xl bg-[#121A2D] flex justify-between items-center">
            <span className="text-slate-400">EMA 13 (Signal)</span>
            <span className="font-bold text-white">₹{indicators.ema13}</span>
          </div>
          <div className="p-2.5 rounded-xl bg-[#121A2D] flex justify-between items-center">
            <span className="text-slate-400">EMA 21 (Baseline)</span>
            <span className="font-bold text-white">₹{indicators.ema21}</span>
          </div>
          <div className="p-2.5 rounded-xl bg-[#121A2D] flex justify-between items-center">
            <span className="text-slate-400">EMA 50 (Trend)</span>
            <span className="font-bold text-white">₹{indicators.ema50}</span>
          </div>
        </div>
      </div>

      {/* Simulated 5-Minute Candle Bar chart preview */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="font-black text-slate-400 uppercase font-mono">Recent 5-Min Volume Activity</span>
          <span className="text-cyan-400 font-mono text-[10px]">Real-time tick flow</span>
        </div>
        <div className="h-16 flex items-end justify-between space-x-1.5 pt-2">
          {[45, 62, 38, 85, 70, 92, 54, 78, 65, 88, 95, 60, 82, 100, 75].map((h, i) => (
            <div key={i} className="flex-1 flex flex-col items-center">
              <div
                className={`w-full rounded-t-sm ${i % 2 === 0 ? 'bg-emerald-500/70' : 'bg-rose-500/70'}`}
                style={{ height: `${h}%` }}
              ></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
