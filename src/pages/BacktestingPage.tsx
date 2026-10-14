import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { History, AlertTriangle } from 'lucide-react';

export const BacktestingPage: React.FC = () => {
  const { selectedIndex } = useTrading();
  const [strategy, setStrategy] = useState('5_LAYER_QUANT_CONFLUENCE');
  const [days, setDays] = useState(30);
  const [statusMessage, setStatusMessage] = useState(
    'NOT RUN — verified historical candles and a real backtest endpoint are not connected.',
  );

  const handleRunBacktest = () => {
    setStatusMessage(
      `BACKTEST BLOCKED for ${selectedIndex}: no verified historical-data/backtest endpoint is wired into this page. Strategy: ${strategy}; period: ${days} days. No performance metrics have been generated.`,
    );
  };

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto font-mono">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="text-sm font-black text-white uppercase">QUANT STRATEGY BACKTESTER</div>
          <div className="text-xs text-slate-400 mt-0.5">Historical candles • fees • slippage • no-lookahead validation</div>
        </div>
        <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400"><History className="w-5 h-5" /></div>
      </div>

      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3 text-xs">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-slate-400 block mb-1">Strategy Architecture</label>
            <select value={strategy} onChange={e => setStrategy(e.target.value)} className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white">
              <option value="5_LAYER_QUANT_CONFLUENCE">5-Layer Quant Confluence</option>
              <option value="SMC_ORDER_BLOCK_PULLBACK">SMC Order Block & FVG</option>
              <option value="EMA_MOMENTUM_BREAKOUT">EMA 8/13 Crossover + VWAP</option>
            </select>
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Sample Period (Days)</label>
            <input type="number" min={1} max={3650} value={days} onChange={e => setDays(Math.max(1, Math.min(3650, parseInt(e.target.value, 10) || 30)))} className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white" />
          </div>
        </div>
        <button onClick={handleRunBacktest} className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#070B12] font-black text-xs flex items-center justify-center space-x-2 mt-2">
          <History className="w-4 h-4" />
          <span>CHECK BACKTEST READINESS</span>
        </button>
      </div>

      <div className="card-base p-4 border border-amber-500/40 bg-amber-500/5 space-y-3">
        <div className="flex items-center gap-2 text-amber-300 font-bold text-xs">
          <AlertTriangle className="w-4 h-4" />
          <span>REAL BACKTEST NOT AVAILABLE</span>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">{statusMessage}</p>
        <p className="text-[11px] text-slate-400 leading-relaxed">
          Win rate, profit factor, drawdown, net P&amp;L and equity curve are intentionally hidden until calculated from timestamped historical data with brokerage, taxes, slippage, contract lot size and out-of-sample checks.
        </p>
      </div>
    </div>
  );
};
