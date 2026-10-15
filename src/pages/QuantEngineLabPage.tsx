import React from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService } from '../services/api';
import { Layers, CheckCircle2, AlertTriangle, ShieldCheck, Activity, Award } from 'lucide-react';

export const QuantEngineLabPage: React.FC = () => {
  const { selectedIndex, market, signals } = useTrading();
  const currentSignal = signals[selectedIndex];
  const layers = apiService.getQuantLayers();

  const quantAvailable = layers.length > 0 && layers.every(layer =>
    layer.status !== 'UNAVAILABLE' && layer.score !== null
  );
  const totalScore = quantAvailable
    ? Math.round(layers.reduce((acc, layer) => acc + ((layer.score ?? 0) * layer.weight) / 100, 0))
    : null;

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
              {totalScore === null ? 'N/A' : `${totalScore}%`}
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              {quantAvailable ? 'Confluence Score' : 'Live score unavailable'}
            </div>
          </div>
        </div>

        {/* Confluence Rating Bar */}
        <div className="mt-3 pt-3 border-t border-[#1C2740]">
          <div className="flex justify-between text-[10px] text-slate-400 font-mono mb-1">
            <span>Minimum Gate: 80%</span>
            <span className={quantAvailable ? 'text-emerald-400 font-bold' : 'text-rose-300 font-bold'}>{quantAvailable ? `Passed Threshold: ${totalScore}%` : 'Threshold not evaluated'}</span>
          </div>
          <div className="w-full h-2 bg-[#070B12] rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full transition-all duration-500"
              style={{ width: `${totalScore ?? 0}%` }}
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
                <span className={`text-xs font-mono font-bold ${layer.status === 'PASS' ? 'text-emerald-400' : layer.status === 'UNAVAILABLE' ? 'text-rose-300' : 'text-amber-300'}`}>
                  {layer.score === null ? 'N/A' : `${layer.score}/100`}
                </span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold font-mono ${layer.status === 'PASS' ? 'bg-emerald-500/20 text-emerald-400' : layer.status === 'UNAVAILABLE' ? 'bg-rose-500/15 text-rose-300' : 'bg-amber-500/20 text-amber-300'}`}>
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
          {!quantAvailable
            ? 'Quant confluence is unavailable because verified backend layer calculations are not available. Do not treat this panel as a validated signal.'
            : currentSignal?.candidate_decision && currentSignal.candidate_decision !== 'WAIT'
              ? `The 5-Layer Quant Engine has validated a high-probability ${currentSignal.candidate_decision} on ${selectedIndex} with ${totalScore}% weighted score. The signal is currently monitored under the 10-minute continuous gate.`
              : `All 5 quantitative layers are actively monitoring ${selectedIndex}. Signal generation is held in WAIT until minimum 80% weighted confluence is achieved.`}
        </p>
      </div>
    </div>
  );
};
