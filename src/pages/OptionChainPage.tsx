import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { OptionChainRow } from '../types/market';
import { apiService, INDEX_CONFIG } from '../services/api';
import { Table2, Wallet, ArrowUpDown } from 'lucide-react';

export const OptionChainPage: React.FC = () => {
  const { selectedIndex, market, executePaperTrade, setActiveTab } = useTrading();
  const currentMarket = market[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];

  const strikes = currentMarket?.option_chain || [];
  const marketActionable = apiService.isFreshLiveMarketRow(currentMarket);
  const ltp = marketActionable ? currentMarket!.ltp : null;

  const [selectedStrike, setSelectedStrike] = useState<{
    row: OptionChainRow;
    side: 'CE' | 'PE';
  } | null>(null);

  const handleOrder = (side: 'CE' | 'PE', row: OptionChainRow) => {
    if (!marketActionable) {
      alert('Paper order blocked: live, fresh broker/exchange market data is unavailable. Preview prices cannot be traded.');
      return;
    }
    const price = side === 'CE' ? row.ce_ltp : row.pe_ltp;
    if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(row.strike) || row.strike <= 0) {
      alert('Paper order blocked: invalid option quote.');
      return;
    }
    executePaperTrade({
      symbol: selectedIndex,
      option_name: `${selectedIndex} ${row.strike} ${side}`,
      side,
      action: 'BUY',
      lots: 2,
      entry_price: price,
      stop_loss: Number((price * 0.8).toFixed(1)),
      target: Number((price * 1.4).toFixed(1)),
    });
    setActiveTab('Paper Trading');
  };

  return (
    <div className="p-3 pb-8 space-y-3 select-none max-w-4xl mx-auto">
      {/* Header bar with Spot Price, PCR, and Max Pain */}
      <div className="card-base p-3.5 border border-[#1C2740] bg-[#101726] flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold text-slate-400 font-mono">
            {selectedIndex} SPOT
          </div>
          <div className="text-lg font-black text-white font-mono">
            ₹{ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div className="flex items-center space-x-4 text-right">
          <div>
            <div className="text-[10px] text-slate-400 font-mono">PCR</div>
            <div className="text-sm font-bold text-emerald-400 font-mono">
              {marketActionable ? currentMarket?.pcr ?? 'N/A' : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-400 font-mono">MAX PAIN</div>
            <div className="text-sm font-bold text-cyan-400 font-mono">
              {marketActionable ? currentMarket?.max_pain ?? 'N/A' : 'N/A'}
            </div>
          </div>
        </div>
      </div>

      {/* Instruction hint */}
      <div className="text-[11px] text-slate-400 px-1 flex items-center justify-between">
        <span>{marketActionable ? 'Tap any CE or PE quote to place a paper order' : 'OFFLINE — live option quotes unavailable; no preview prices shown'}</span>
        <span className="text-cyan-400 font-mono">Lot Size: {cfg.lotSize}</span>
      </div>

      {/* Option Chain Table */}
      <div className="card-base border border-[#1C2740] bg-[#0E1524] overflow-x-auto rounded-xl">
        <table className="w-full text-center text-xs font-mono border-collapse">
          <thead>
            <tr className="bg-[#070B12] text-slate-400 border-b border-[#1C2740] text-[10px]">
              <th className="py-2.5 px-2 text-emerald-400 font-bold" colSpan={3}>
                CALLS (CE)
              </th>
              <th className="py-2.5 px-3 bg-[#121A2D] text-white font-black">
                STRIKE
              </th>
              <th className="py-2.5 px-2 text-rose-400 font-bold" colSpan={3}>
                PUTS (PE)
              </th>
            </tr>
            <tr className="bg-[#0A0F1A] text-slate-500 border-b border-[#1C2740] text-[9px] uppercase">
              <th className="py-1 px-1.5">OI</th>
              <th className="py-1 px-1.5">Vol</th>
              <th className="py-1 px-2 text-right">LTP</th>
              <th className="py-1 px-3 bg-[#121A2D] text-cyan-400">ATM</th>
              <th className="py-1 px-2 text-left">LTP</th>
              <th className="py-1 px-1.5">Vol</th>
              <th className="py-1 px-1.5">OI</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#17223B]">
            {strikes.length === 0 && (
              <tr>
                <td colSpan={7} className="py-8 px-3 text-center text-slate-400">
                  Live option-chain data unavailable. Reconnect to the verified signal backend; no synthetic quotes are shown.
                </td>
              </tr>
            )}
            {strikes.map(row => {
              const isAtm = row.is_atm;

              return (
                <tr
                  key={row.strike}
                  className={`transition-colors hover:bg-[#17223B]/60 ${
                    isAtm ? 'bg-cyan-500/10 font-bold' : ''
                  }`}
                >
                  {/* Call OI */}
                  <td className="py-2 px-1.5 text-slate-400 text-[10px]">
                    {(row.ce_oi / 1000).toFixed(0)}k
                  </td>
                  {/* Call Volume */}
                  <td className="py-2 px-1.5 text-slate-400 text-[10px]">
                    {(row.ce_volume / 1000).toFixed(0)}k
                  </td>
                  {/* Call LTP (Clickable) */}
                  <td className="py-2 px-2 text-right">
                    <button
                      onClick={() => handleOrder('CE', row)}
                      disabled={!marketActionable}
                      className="px-2 py-1 rounded bg-[#101726] hover:bg-emerald-500/20 text-emerald-400 font-bold text-xs transition-all active:scale-95 border border-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      ₹{row.ce_ltp}
                    </button>
                  </td>

                  {/* STRIKE (Center) */}
                  <td
                    className={`py-2 px-3 bg-[#121A2D] font-black text-xs ${
                      isAtm ? 'text-cyan-400' : 'text-slate-100'
                    }`}
                  >
                    <div className="flex items-center justify-center space-x-1">
                      <span>{row.strike}</span>
                      {isAtm && (
                        <span className="text-[8px] bg-cyan-400 text-[#070B12] px-1 rounded font-bold">
                          ATM
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Put LTP (Clickable) */}
                  <td className="py-2 px-2 text-left">
                    <button
                      onClick={() => handleOrder('PE', row)}
                      disabled={!marketActionable}
                      className="px-2 py-1 rounded bg-[#101726] hover:bg-rose-500/20 text-rose-400 font-bold text-xs transition-all active:scale-95 border border-rose-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      ₹{row.pe_ltp}
                    </button>
                  </td>
                  {/* Put Volume */}
                  <td className="py-2 px-1.5 text-slate-400 text-[10px]">
                    {(row.pe_volume / 1000).toFixed(0)}k
                  </td>
                  {/* Put OI */}
                  <td className="py-2 px-1.5 text-slate-400 text-[10px]">
                    {(row.pe_oi / 1000).toFixed(0)}k
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
