import React from 'react';
import { useTrading } from '../context/TradingContext';
import { INDEX_CONFIG } from '../services/api';
import { BarChart3, TrendingUp, TrendingDown, ArrowUpDown } from 'lucide-react';

export const OILabPage: React.FC = () => {
  const { selectedIndex, market } = useTrading();
  const currentMarket = market[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];
  const ageMs = currentMarket?.timestamp ? Date.now() - Date.parse(currentMarket.timestamp) : Number.POSITIVE_INFINITY;
  const isLive = Boolean(currentMarket?.live === true && Number.isFinite(ageMs) && ageMs >= 0 && ageMs <= 120000);
  const ltp = isLive ? currentMarket?.ltp : null;
  const strikes = isLive && Array.isArray(currentMarket?.option_chain) ? currentMarket.option_chain : [];

  const totalCallOI = strikes.reduce((acc, s) => acc + s.ce_oi, 0);
  const totalPutOI = strikes.reduce((acc, s) => acc + s.pe_oi, 0);
  const pcr = strikes.length > 0 && totalCallOI > 0 ? Number((totalPutOI / totalCallOI).toFixed(2)) : null;

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-3xl mx-auto">
      {/* Top Banner */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div>
          <div className="text-sm font-black text-white font-mono uppercase">
            {selectedIndex} OPEN INTEREST LAB
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Total Calls: {strikes.length ? (totalCallOI / 100000).toFixed(1) + 'L' : '—'} • Total Puts: {strikes.length ? (totalPutOI / 100000).toFixed(1) + 'L' : '—'}
          </div>
        </div>

        <div className="text-right">
          <div className="text-2xl font-black text-emerald-400 font-mono">
            {pcr ?? '—'}
          </div>
          <div className="text-[10px] text-slate-400 font-mono">
            Overall PCR Ratio
          </div>
        </div>
      </div>

      {!isLive || strikes.length === 0 ? (
        <div className="card-base p-4 border border-amber-500/40 bg-amber-500/5 text-xs text-amber-200 space-y-2">
          <div className="font-bold">LIVE OPTION CHAIN UNAVAILABLE</div>
          <p>Open interest, PCR and strike bars are withheld because no fresh, broker-validated option-chain snapshot is available. No default PCR or synthetic strikes are displayed.</p>
        </div>
      ) : null}

      {/* OI Distribution Bar Graph */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3 font-mono">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span className="font-bold text-emerald-400">Call OI (Resistance)</span>
          <span className="font-bold text-white">Strike Ladder</span>
          <span className="font-bold text-rose-400">Put OI (Support)</span>
        </div>

        <div className="space-y-2 pt-1">
          {strikes.slice(2, 13).map(row => {
            const maxOI = Math.max(...strikes.map(s => Math.max(s.ce_oi, s.pe_oi)));
            const cePercent = (row.ce_oi / maxOI) * 100;
            const pePercent = (row.pe_oi / maxOI) * 100;
            const isAtm = row.is_atm;

            return (
              <div key={row.strike} className="flex items-center space-x-2 text-xs">
                {/* Call OI Bar (Left) */}
                <div className="flex-1 flex justify-end items-center space-x-1.5">
                  <span className="text-[10px] text-slate-400">{(row.ce_oi / 1000).toFixed(0)}k</span>
                  <div className="w-24 h-3 bg-[#070B12] rounded-l overflow-hidden flex justify-end">
                    <div
                      className="h-full bg-emerald-500 rounded-l"
                      style={{ width: `${cePercent}%` }}
                    ></div>
                  </div>
                </div>

                {/* Strike Center */}
                <div
                  className={`w-16 py-0.5 rounded text-center text-xs font-bold ${
                    isAtm ? 'bg-cyan-500 text-[#070B12]' : 'bg-[#0E1524] text-slate-200'
                  }`}
                >
                  {row.strike}
                </div>

                {/* Put OI Bar (Right) */}
                <div className="flex-1 flex justify-start items-center space-x-1.5">
                  <div className="w-24 h-3 bg-[#070B12] rounded-r overflow-hidden">
                    <div
                      className="h-full bg-rose-500 rounded-r"
                      style={{ width: `${pePercent}%` }}
                    ></div>
                  </div>
                  <span className="text-[10px] text-slate-400">{(row.pe_oi / 1000).toFixed(0)}k</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
