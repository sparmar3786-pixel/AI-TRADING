import React from 'react';
import { useTrading } from '../context/TradingContext';
import { IndexSymbol } from '../types/market';

const INDICES: IndexSymbol[] = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX'];

export const IndexSelector: React.FC = () => {
  const { selectedIndex, setSelectedIndex, market } = useTrading();

  return (
    <div className="w-full bg-[#070B12] px-3 py-2 border-b border-[#121A2D] overflow-x-auto no-scrollbar flex items-center space-x-2 select-none">
      {INDICES.map(idx => {
        const isSelected = selectedIndex === idx;
        const row = market[idx];
        const ltp = row ? row.ltp.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '...';
        const isPositive = row ? row.change >= 0 : true;
        const changePercent = row ? `${isPositive ? '+' : ''}${row.change_percent.toFixed(2)}%` : '0.00%';

        return (
          <button
            key={idx}
            onClick={() => setSelectedIndex(idx)}
            className={`flex flex-col items-start px-3 py-1.5 rounded-xl transition-all duration-150 flex-shrink-0 text-left border ${
              isSelected
                ? 'bg-cyan-500/15 border-cyan-400 text-white shadow-sm shadow-cyan-500/20'
                : 'bg-[#0E1524] border-[#1C2740] text-slate-300 hover:border-slate-600'
            }`}
          >
            <div className="flex items-center space-x-1.5 w-full">
              <span className={`text-[11px] font-black tracking-wide font-mono ${isSelected ? 'text-cyan-400' : 'text-slate-200'}`}>
                {idx}
              </span>
              <span className={`text-[10px] font-bold font-mono ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                {changePercent}
              </span>
            </div>
            <div className="text-[12px] font-bold text-slate-100 font-mono mt-0.5">
              ₹{ltp}
            </div>
          </button>
        );
      })}
    </div>
  );
};
