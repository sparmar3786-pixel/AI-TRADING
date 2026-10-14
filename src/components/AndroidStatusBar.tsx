import React from 'react';
import { Wifi, Battery, Radio } from 'lucide-react';
import { useTrading } from '../context/TradingContext';

export const AndroidStatusBar: React.FC = () => {
  const { marketStatus } = useTrading();
  
  // Format current local time for the Android status clock
  const currentTime = new Date().toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  return (
    <div className="w-full bg-[#070B12] text-slate-300 text-xs px-4 pt-1.5 pb-1 flex items-center justify-between border-b border-[#121A2D] select-none z-50">
      <div className="flex items-center space-x-2">
        <span className="font-semibold text-slate-200 tracking-tight font-mono">{currentTime}</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#121A2D] text-cyan-400 font-mono">
          {marketStatus.istTime}
        </span>
      </div>

      <div className="flex items-center space-x-2 text-slate-400">
        <div className="flex items-center space-x-1">
          <span className="text-[10px] font-bold text-slate-300">5G</span>
          <Radio className="w-3.5 h-3.5 text-slate-300" />
        </div>
        <Wifi className="w-3.5 h-3.5 text-slate-300" />
        <div className="flex items-center space-x-1">
          <span className="text-[10px] font-medium text-slate-300">98%</span>
          <Battery className="w-4 h-4 text-emerald-400 fill-emerald-400" />
        </div>
      </div>
    </div>
  );
};
