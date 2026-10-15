import React from 'react';
import { useTrading } from '../context/TradingContext';
import { CommoditySymbol } from '../types/market';
import { COMMODITY_CONFIG } from '../services/api';
import { Flame, TrendingUp, TrendingDown, Clock } from 'lucide-react';

export const CommoditiesPage: React.FC = () => {
  const { commodities, marketStatus, selectedCommodity, setSelectedCommodity } = useTrading();

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      {/* MCX Market Status Banner */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <Flame className="w-5 h-5 text-amber-400" />
            <span className="text-sm font-black text-white font-mono uppercase">
              MCX Commodity Exchange
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Trading Hours: 09:00 AM - 11:30 PM IST (Active)
          </div>
        </div>

        <div className="text-right">
          <span
            className={`inline-flex items-center space-x-1 px-2.5 py-1 rounded-xl text-xs font-bold font-mono ${
              marketStatus.mcxOpen
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-live-blink"></span>
            <span>{marketStatus.mcxOpen ? 'MCX OPEN' : 'MCX CLOSED'}</span>
          </span>
          <div className="text-[10px] text-slate-400 font-mono mt-1">
            {marketStatus.istTime}
          </div>
        </div>
      </div>

      {/* Commodity Cards Grid */}
      <div className="space-y-3">
        {commodities.map(comm => {
          const isPositive = comm.change >= 0;
          const isSelected = selectedCommodity === comm.symbol;

          return (
            <div
              key={comm.symbol}
              onClick={() => setSelectedCommodity(comm.symbol)}
              className={`card-base p-4 border transition-all cursor-pointer ${
                isSelected
                  ? 'border-cyan-400 bg-[#141E34] shadow-md shadow-cyan-500/10'
                  : 'border-[#1C2740] bg-[#101726] hover:bg-[#121A2D]'
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-black text-white font-mono">
                      {comm.symbol}
                    </span>
                    <span className="text-xs text-slate-400">
                      {comm.name}
                    </span>
                  </div>
                  <div className="text-xl font-black text-white font-mono mt-1">
                    ₹{comm.ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    <span className="text-xs text-slate-400 font-normal ml-1.5">
                      {comm.unit}
                    </span>
                  </div>
                </div>

                <div className="text-right">
                  <div
                    className={`inline-flex items-center space-x-1 px-2.5 py-1 rounded-xl text-xs font-bold font-mono ${
                      isPositive
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                    }`}
                  >
                    {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                    <span>{isPositive ? '+' : ''}{comm.change.toFixed(2)} ({isPositive ? '+' : ''}{comm.change_percent.toFixed(2)}%)</span>
                  </div>

                  <div className="text-[10px] text-slate-400 font-mono mt-1.5">
                    Vol: {(comm.volume / 1000).toFixed(1)}k • OI: {(comm.oi / 1000).toFixed(1)}k
                  </div>
                </div>
              </div>

              {/* Day High / Low row */}
              <div className="mt-3 pt-2.5 border-t border-[#1C2740] flex justify-between text-[11px] text-slate-400 font-mono">
                <span>Low: ₹{comm.low.toLocaleString('en-IN')}</span>
                <span>Open: ₹{comm.open.toLocaleString('en-IN')}</span>
                <span>High: ₹{comm.high.toLocaleString('en-IN')}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
