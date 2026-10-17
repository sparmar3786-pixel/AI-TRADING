import React from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService } from '../services/api';
import { Layers, CheckCircle2, AlertTriangle, ShieldCheck, Activity, Award } from 'lucide-react';

export const QuantEngineLabPage: React.FC = () => {
  const { selectedIndex, market, signals } = useTrading();
  const currentSignal = signals[selectedIndex];
  const layers = apiService.getQuantLayers(currentSignal);
  const reportedLayers = layers.filter(layer => layer.status !== 'UNAVAILABLE').length;
  const passedLayers = layers.filter(layer => layer.status === 'PASS').length;
  const failedLayers = layers.filter(layer => layer.status === 'FAIL').length;
  const allLayersReported = reportedLayers === 5;
  const hasLayerEvidence = reportedLayers > 0;
  const serverConfirmed = currentSignal?.signal_stability?.state === 'CONFIRMED' &&
    currentSignal?.signal_stability?.server_confirmed === true;


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
              {!hasLayerEvidence ? 'N/A' : `${passedLayers}/${reportedLayers}`}
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              {hasLayerEvidence ? 'Backend gates passing / reported' : 'Backend evidence unavailable'}
            </div>
          </div>
        </div>

        {/* Confluence Rating Bar */}
        <div className="mt-3 pt-3 border-t border-[#1C2740]">
          <div className="flex justify-between text-[10px] text-slate-400 font-mono mb-1">
            <span>Five mandatory backend rule gates</span>
            <span className={allLayersReported && passedLayers === 5 ? 'text-emerald-400 font-bold' : 'text-amber-300 font-bold'}>{!hasLayerEvidence ? 'No backend result' : `${reportedLayers}/5 reported • ${passedLayers} PASS • ${failedLayers} FAIL`}</span>
          </div>
          <div className="w-full h-2 bg-[#070B12] rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full transition-all duration-500"
              style={{ width: `${hasLayerEvidence ? Math.round((passedLayers / 5) * 100) : 0}%` }}
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
                  {layer.score === null ? 'Rule gate' : `${layer.score}/100`}
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
              Backend evidence only • not a profit probability
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
          {!allLayersReported
            ? `Verified backend evidence is incomplete for ${selectedIndex}: ${reportedLayers}/5 layer results are present. Missing layers remain UNAVAILABLE; no local scores are fabricated.`
            : failedLayers > 0
              ? `${passedLayers}/5 backend rule gates passed and ${failedLayers} failed. The five-layer result is a validation checklist, not a probability of profit.`
              : serverConfirmed
                ? `All five backend rule gates passed and the server reports a confirmed stability state for ${selectedIndex}. This remains informational only; it is not a broker fill or profitability guarantee.`
                : `All five backend rule checks passed, but the final signal is not server-confirmed. Keep the decision in WAIT until the server-owned validation and 600-second gate are verified.`}
        </p>
      </div>
    </div>
  );
};
