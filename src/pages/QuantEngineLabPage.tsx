import React from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService } from '../services/api';
import { Layers, CheckCircle2, AlertTriangle, ShieldCheck, Activity, Award } from 'lucide-react';

export const QuantEngineLabPage: React.FC = () => {
  const { selectedIndex, market, signals } = useTrading();
  const currentSignal = signals[selectedIndex];
  const layers = apiService.getQuantLayers();

  const totalScore = Math.round(
    layers.reduce((acc, l) => acc + (l.score * l.weight) / 100, 0)
  );

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      {/* Header Confluence Card */}
      <div className="card-base p-4 border border-[#1C2740] bg-gradient-to-r from-[#121A2D] to-[#0E1524]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-black text-cyan-400 font-mono tracking-widest uppercase">
              5-Layer Quant Engine
            </div>
            <div className="text-sm font-bold text-white mt-0.5">
              Multi-Factor Signal Confluence • {selectedIndex}
            </div>
          </div>

          <div className="text-right">
            <div className="text-2xl font-black text-emerald-400 font-mono">
              {totalScore}%
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              Confluence Score
            </div>
          </div>
        </div>

        {/* Confluence Rating Bar */}
        <div className="mt-3 pt-3 border-t border-[#1C2740]">
          <div className="flex justify-between text-[10px] text-slate-400 font-mono mb-1">
            <span>Minimum Gate: 80%</span>
            <span className="text-emerald-400 font-bold">Passed Threshold: {totalScore}%</span>
          </div>
          <div className="w-full h-2 bg-[#070B12] rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full transition-all duration-500"
              style={{ width: `${totalScore}%` }}
            ></div>
          </div>
        </div>
      </div>

      {/* 5 Layer Cards */}
      <div className="space-y-2.5">
        <div className="text-xs font-black text-slate-400 uppercase tracking-wider font-mono px-1">
          Quantitative Layer Analysis
        </div>

        {layers.map(layer => (
          <div
            key={layer.layer}
            className="card-base p-3.5 border border-[#1C2740] bg-[#101726] space-y-1.5"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-xs font-black font-mono flex items-center justify-center">
                  L{layer.layer}
                </span>
                <span className="text-xs font-bold text-white">
                  {layer.name}
                </span>
              </div>

              <div className="flex items-center space-x-2">
                <span className="text-xs font-mono font-bold text-emerald-400">
                  {layer.score}/100
                </span>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 font-mono">
                  {layer.status}
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-300 font-mono pl-7">
              {layer.detail}
            </p>

            <div className="pl-7 text-[10px] text-slate-500 font-mono">
              Engine weight: {layer.weight}%
            </div>
          </div>
        ))}
      </div>

      {/* Validation verdict */}
      <div className="card-base p-3.5 border border-[#1C2740] bg-[#0E1524]">
        <div className="flex items-center space-x-2 text-xs font-bold text-cyan-400 mb-1">
          <ShieldCheck className="w-4 h-4" />
          <span>ALGO CONFLUENCE SUMMARY</span>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">
          {currentSignal?.candidate_decision && currentSignal.candidate_decision !== 'WAIT'
            ? `The 5-Layer Quant Engine has validated a high-probability ${currentSignal.candidate_decision} on ${selectedIndex} with ${totalScore}% weighted score. The signal is currently monitored under the 10-minute continuous gate.`
            : `All 5 quantitative layers are actively monitoring ${selectedIndex}. Signal generation is held in WAIT until minimum 80% weighted confluence is achieved.`}
        </p>
      </div>
    </div>
  );
};
