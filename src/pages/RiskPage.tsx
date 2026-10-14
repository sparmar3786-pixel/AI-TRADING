import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { INDEX_CONFIG } from '../services/api';
import { ShieldAlert, Calculator, DollarSign, AlertCircle } from 'lucide-react';

export const RiskPage: React.FC = () => {
  const { selectedIndex, paperBalance } = useTrading();
  const cfg = INDEX_CONFIG[selectedIndex];

  const [capital, setCapital] = useState(paperBalance || 500000);
  const [riskPercent, setRiskPercent] = useState(2);
  const [entryPrice, setEntryPrice] = useState(140);
  const [slPrice, setSlPrice] = useState(110);
  const [targetPrice, setTargetPrice] = useState(200);

  // Risk Math
  const maxRiskAmount = (capital * riskPercent) / 100;
  const slPoints = Math.max(1, entryPrice - slPrice);
  const targetPoints = Math.max(1, targetPrice - entryPrice);
  const riskPerLot = slPoints * cfg.lotSize;
  const recommendedLots = Math.max(1, Math.floor(maxRiskAmount / riskPerLot));
  const maxLoss = recommendedLots * riskPerLot;
  const maxGain = recommendedLots * (targetPoints * cfg.lotSize);
  const rrRatio = (targetPoints / slPoints).toFixed(2);

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      {/* Header */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="text-sm font-black text-white font-mono uppercase">
            RISK & POSITION SIZING
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Mathematical Capital Preservation Engine • {selectedIndex}
          </div>
        </div>

        <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400">
          <Calculator className="w-5 h-5" />
        </div>
      </div>

      {/* Input controls */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3 font-mono text-xs">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-slate-400 block mb-1">Trading Capital (₹)</label>
            <input
              type="number"
              value={capital}
              onChange={e => setCapital(parseFloat(e.target.value) || 0)}
              className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Max Risk per Trade (%)</label>
            <input
              type="number"
              step="0.5"
              value={riskPercent}
              onChange={e => setRiskPercent(parseFloat(e.target.value) || 0)}
              className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-cyan-400 font-bold"
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 pt-2">
          <div>
            <label className="text-slate-400 block mb-1">Entry (₹)</label>
            <input
              type="number"
              value={entryPrice}
              onChange={e => setEntryPrice(parseFloat(e.target.value) || 0)}
              className="w-full p-2 rounded-xl bg-[#070B12] border border-[#1C2740] text-white text-center"
            />
          </div>
          <div>
            <label className="text-rose-400 block mb-1">Stop Loss (₹)</label>
            <input
              type="number"
              value={slPrice}
              onChange={e => setSlPrice(parseFloat(e.target.value) || 0)}
              className="w-full p-2 rounded-xl bg-[#070B12] border border-[#1C2740] text-rose-300 text-center"
            />
          </div>
          <div>
            <label className="text-emerald-400 block mb-1">Target (₹)</label>
            <input
              type="number"
              value={targetPrice}
              onChange={e => setTargetPrice(parseFloat(e.target.value) || 0)}
              className="w-full p-2 rounded-xl bg-[#070B12] border border-[#1C2740] text-emerald-300 text-center"
            />
          </div>
        </div>
      </div>

      {/* Recommended Output */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] space-y-3 font-mono">
        <div className="text-xs font-black text-cyan-400 uppercase tracking-wider">
          Algorithmically Recommended Position
        </div>

        <div className="grid grid-cols-2 gap-3 text-center">
          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-[10px] text-slate-400">SAFE POSITION SIZE</div>
            <div className="text-2xl font-black text-cyan-400 mt-1">
              {recommendedLots} Lots
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              {recommendedLots * cfg.lotSize} Quantity ({cfg.lotSize}/lot)
            </div>
          </div>

          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-[10px] text-slate-400">RISK : REWARD</div>
            <div className="text-2xl font-black text-emerald-400 mt-1">
              1 : {rrRatio}
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              SL {slPoints} pts • Target {targetPoints} pts
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-center text-xs pt-1">
          <div className="p-2 rounded-lg bg-[#070B12]">
            <div className="text-[10px] text-rose-400">MAX LOSS ON SL</div>
            <div className="font-bold text-rose-300 mt-0.5">₹{maxLoss.toLocaleString('en-IN')}</div>
          </div>
          <div className="p-2 rounded-lg bg-[#070B12]">
            <div className="text-[10px] text-emerald-400">EXPECTED GAIN ON TARGET</div>
            <div className="font-bold text-emerald-300 mt-0.5">₹{maxGain.toLocaleString('en-IN')}</div>
          </div>
        </div>
      </div>
    </div>
  );
};
