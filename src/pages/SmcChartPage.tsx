import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService, INDEX_CONFIG } from '../services/api';
import { LineChart, Zap, Eye, BarChart2, Shield } from 'lucide-react';

export const SmcChartPage: React.FC = () => {
  const { selectedIndex, market } = useTrading();
  const currentMarket = market[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];
  const ltp = currentMarket?.ltp || cfg.basePrice;

  const [timeframe, setTimeframe] = useState<'1m' | '3m' | '5m' | '15m'>('5m');
  const smc = apiService.getSmcStructure(ltp);

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-3xl mx-auto">
      {/* Top Header & Timeframe Switcher */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-sm font-black text-white font-mono">{selectedIndex} SMC PRO</span>
            <span className="text-xs text-cyan-400 font-mono">₹{ltp.toLocaleString('en-IN')}</span>
          </div>
          <div className="text-[10px] text-slate-400 font-medium mt-0.5">
            Smart Money Institutional Order Blocks & Liquidity
          </div>
        </div>

        {/* Timeframe Chips */}
        <div className="flex items-center space-x-1 bg-[#070B12] p-1 rounded-xl border border-[#1C2740]">
          {(['1m', '3m', '5m', '15m'] as const).map(tf => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-2.5 py-1 text-xs font-bold rounded-lg font-mono transition-all ${
                timeframe === tf
                  ? 'bg-cyan-500 text-[#070B12]'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* SMC Candlestick Canvas & Structure Visualizer */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#0E1524] space-y-3 relative overflow-hidden">
        <div className="flex items-center justify-between text-xs font-mono">
          <div className="flex items-center space-x-2">
            <span className="text-emerald-400 font-bold">Trend: {smc.trend}</span>
            <span className="text-slate-500">•</span>
            <span className="text-slate-300">BOS: {smc.last_bos.price}</span>
            <span className="text-slate-500">•</span>
            <span className="text-slate-300">CHoCH: {smc.last_choch.price}</span>
          </div>
          <div className="text-[10px] text-cyan-400 font-mono">
            {timeframe} TF Active
          </div>
        </div>

        {/* Visual Simulated Candlestick Chart Area with SMC Zones */}
        <div className="w-full h-64 bg-[#070B12] rounded-xl border border-[#1C2740] relative p-3 flex flex-col justify-between overflow-hidden">
          {/* Bearish Order Block Zone Overlay */}
          <div
            className="absolute left-0 right-0 border-t border-b border-rose-500/40 bg-rose-500/10 flex items-center justify-between px-3 text-[10px] text-rose-300 font-mono"
            style={{ top: '15%', height: '14%' }}
          >
            <span>Bearish Order Block (OB): ₹{smc.order_blocks[1].high}</span>
            <span className="text-[9px] bg-rose-500/20 px-1.5 py-0.5 rounded">UNMITIGATED</span>
          </div>

          {/* Current LTP Horizontal Axis Line */}
          <div
            className="absolute left-0 right-0 border-b border-dashed border-cyan-400 flex items-center justify-end pr-2 text-[10px] text-cyan-400 font-mono font-bold z-10"
            style={{ top: '48%' }}
          >
            <span className="bg-[#070B12] px-1.5 py-0.5 rounded border border-cyan-400/50">
              LTP ₹{ltp}
            </span>
          </div>

          {/* Bullish Order Block Zone Overlay */}
          <div
            className="absolute left-0 right-0 border-t border-b border-emerald-500/40 bg-emerald-500/10 flex items-center justify-between px-3 text-[10px] text-emerald-300 font-mono"
            style={{ bottom: '15%', height: '15%' }}
          >
            <span>Bullish Order Block (OB): ₹{smc.order_blocks[0].high}</span>
            <span className="text-[9px] bg-emerald-500/20 px-1.5 py-0.5 rounded">HIGH DEMAND</span>
          </div>

          {/* Candlestick bars in background */}
          <div className="absolute inset-0 flex items-center justify-between px-6 opacity-80 pointer-events-none">
            {[
              { o: 60, c: 75, h: 85, l: 50, bull: true },
              { o: 75, c: 68, h: 80, l: 62, bull: false },
              { o: 68, c: 80, h: 88, l: 65, bull: true },
              { o: 80, c: 72, h: 84, l: 70, bull: false },
              { o: 72, c: 85, h: 90, l: 68, bull: true },
              { o: 85, c: 92, h: 96, l: 82, bull: true },
              { o: 92, c: 84, h: 95, l: 80, bull: false },
              { o: 84, c: 76, h: 88, l: 72, bull: false },
              { o: 76, c: 88, h: 92, l: 74, bull: true },
              { o: 88, c: 95, h: 98, l: 85, bull: true },
              { o: 95, c: 89, h: 96, l: 85, bull: false },
              { o: 89, c: 94, h: 97, l: 86, bull: true },
            ].map((c, i) => (
              <div key={i} className="flex flex-col items-center h-48 justify-center relative">
                {/* Wick */}
                <div
                  className={`w-0.5 absolute ${c.bull ? 'bg-emerald-400' : 'bg-rose-400'}`}
                  style={{
                    height: `${(c.h - c.l) * 1.5}px`,
                    top: `${(100 - c.h) * 1.2}px`,
                  }}
                ></div>
                {/* Body */}
                <div
                  className={`w-3 rounded-sm z-0 ${c.bull ? 'bg-emerald-500' : 'bg-rose-500'}`}
                  style={{
                    height: `${Math.max(6, Math.abs(c.c - c.o) * 1.5)}px`,
                  }}
                ></div>
              </div>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-3 pt-2 text-[11px] font-mono text-slate-400">
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-2 rounded bg-emerald-500/40 border border-emerald-500"></span>
            <span>Bullish OB</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-2 rounded bg-rose-500/40 border border-rose-500"></span>
            <span>Bearish OB</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-0.5 bg-cyan-400"></span>
            <span>Spot LTP</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="text-amber-400 font-bold">CHoCH:</span>
            <span>Character Change</span>
          </div>
        </div>
      </div>

      {/* Institutional Liquidity Levels */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
        <div className="text-xs font-black text-slate-400 uppercase tracking-wider font-mono">
          Smart Money Liquidity Pools
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <div className="p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-[10px] text-rose-400">BUY-SIDE LIQUIDITY (BSL)</div>
            <div className="text-sm font-bold text-white mt-1">₹{smc.liquidity_pools[0].level}</div>
            <div className="text-[9px] text-slate-500 mt-0.5">Stops above range high</div>
          </div>
          <div className="p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-[10px] text-emerald-400">SELL-SIDE LIQUIDITY (SSL)</div>
            <div className="text-sm font-bold text-white mt-1">₹{smc.liquidity_pools[1].level}</div>
            <div className="text-[9px] text-emerald-400/80 mt-0.5">Swept & rejected (Reversal trigger)</div>
          </div>
        </div>
      </div>
    </div>
  );
};
