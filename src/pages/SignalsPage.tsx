import React from 'react';
import {
  Zap,
  Clock,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Lock,
  ArrowUpRight,
  TrendingDown,
  Layers,
  Wallet,
} from 'lucide-react';
import { useTrading } from '../context/TradingContext';
import { IndexSymbol } from '../types/market';
import { INDEX_CONFIG } from '../services/api';

const ALL_INDICES: IndexSymbol[] = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX'];

export const SignalsPage: React.FC = () => {
  const { signals, market, executePaperTrade, setActiveTab, setSelectedIndex } = useTrading();

  const handleExecute = (symbol: string, signal: any) => {
    if (!signal.strike || !signal.option_side) return;
    executePaperTrade({
      symbol,
      option_name: `${symbol} ${signal.strike} ${signal.option_side}`,
      side: signal.option_side,
      action: 'BUY',
      lots: 2,
      entry_price: signal.entry || 140,
      stop_loss: signal.stop_loss || 110,
      target: signal.target || 200,
    });
    setActiveTab('Paper Trading');
  };

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      {/* Header explanation of 10-Minute Signal Gate */}
      <div className="card-base p-4 border border-[#1C2740] bg-gradient-to-r from-[#101728] to-[#0E1524]">
        <div className="flex items-start space-x-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-400 mt-0.5">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-sm font-black text-white tracking-wide uppercase font-mono">
              Signal-Only Safeguards & 10m Gate
            </h2>
            <p className="text-xs text-slate-300 mt-1 leading-relaxed">
              To eliminate false breakouts and whipsaws, an algorithmic BUY candidate must pass 5-layer validation and keep the exact same side and strike for <strong className="text-cyan-400">10 continuous minutes (600 seconds)</strong> before it is confirmed as actionable.
            </p>
            <div className="grid grid-cols-2 gap-2 mt-3 text-[10px] text-slate-400 font-mono">
              <div className="flex items-center space-x-1.5">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                <span>60s refresh gap resets gate</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Lock className="w-3.5 h-3.5 text-emerald-400" />
                <span>No direct broker write</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Index Signal Cards */}
      <div className="space-y-3">
        {ALL_INDICES.map(idx => {
          const sig = signals[idx];
          const mkt = market[idx];
          const cfg = INDEX_CONFIG[idx];
          const stability = sig?.signal_stability;
          const isConfirmed = stability?.state === 'CONFIRMED';
          const isConfirming = stability?.state === 'CONFIRMED' ? false : (stability?.state === 'CONFIRMING' || (sig?.candidate_decision && sig.candidate_decision !== 'WAIT'));
          const elapsed = stability?.elapsed_seconds ?? 0;
          const remaining = stability?.remaining_seconds ?? (600 - elapsed);
          const percent = Math.min(100, Math.floor((elapsed / 600) * 100));

          return (
            <div
              key={idx}
              className="card-base p-4 border border-[#1C2740] bg-[#121A2D] space-y-3"
            >
              {/* Header: Index, LTP, and Decision badge */}
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-black text-white font-mono">{idx}</span>
                    <span className="text-xs text-slate-400 font-mono">
                      ₹{mkt ? mkt.ltp.toLocaleString('en-IN') : cfg.basePrice}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-400">
                    Regime: <span className="text-slate-200 font-semibold">{sig?.regime || 'RANGE_BOUND'}</span>
                  </div>
                </div>

                <div>
                  {isConfirmed ? (
                    <span className="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-xs font-black font-mono flex items-center space-x-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>{sig?.decision}</span>
                    </span>
                  ) : isConfirming ? (
                    <span className="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/40 text-xs font-bold font-mono flex items-center space-x-1">
                      <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
                      <span>CONFIRMING ({sig?.candidate_decision})</span>
                    </span>
                  ) : (
                    <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-400 border border-slate-700 text-xs font-bold font-mono">
                      WAIT
                    </span>
                  )}
                </div>
              </div>

              {/* Candidate strike, entry, stop loss, and target */}
              {sig?.candidate_decision && sig.candidate_decision !== 'WAIT' ? (
                <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center space-x-2">
                      <span className="text-cyan-400 font-bold">{sig.strike} {sig.option_side}</span>
                      <span className="text-slate-400">({sig.candidate_decision})</span>
                    </div>
                    <div className="text-slate-300 font-bold">
                      R:R {sig.risk_reward || '1 : 2.0'}
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-center font-mono">
                    <div className="p-1.5 rounded-lg bg-[#0E1524]">
                      <div className="text-[9px] text-slate-400">ENTRY</div>
                      <div className="text-xs font-bold text-white">₹{sig.entry}</div>
                    </div>
                    <div className="p-1.5 rounded-lg bg-[#0E1524]">
                      <div className="text-[9px] text-rose-400">SL</div>
                      <div className="text-xs font-bold text-rose-300">₹{sig.stop_loss}</div>
                    </div>
                    <div className="p-1.5 rounded-lg bg-[#0E1524]">
                      <div className="text-[9px] text-emerald-400">TARGET</div>
                      <div className="text-xs font-bold text-emerald-300">₹{sig.target}</div>
                    </div>
                  </div>

                  {/* 10-Minute Progress Bar */}
                  <div className="space-y-1 pt-1">
                    <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                      <span>Gate Stability</span>
                      <span className="text-cyan-400">{elapsed}s / 600s ({percent}%)</span>
                    </div>
                    <div className="w-full h-1 bg-[#121A2D] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-amber-400 to-emerald-400 rounded-full"
                        style={{ width: `${percent}%` }}
                      ></div>
                    </div>
                  </div>

                  {/* Validation Points */}
                  {sig.reasons && sig.reasons.length > 0 && (
                    <div className="pt-1 border-t border-[#1C2740] text-[10px] text-slate-300 space-y-0.5">
                      {sig.reasons.map((r, i) => (
                        <div key={i} className="flex items-center space-x-1.5">
                          <span className="w-1 h-1 rounded-full bg-cyan-400"></span>
                          <span>{r}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Execute Button */}
                  <div className="pt-1 flex items-center space-x-2">
                    <button
                      onClick={() => handleExecute(idx, sig)}
                      className="w-full py-1.5 px-3 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-[#070B12] font-black text-xs font-mono flex items-center justify-center space-x-1.5 active:scale-95 transition-all"
                    >
                      <Wallet className="w-3.5 h-3.5" />
                      <span>SIMULATE PAPER TRADE</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="p-2.5 rounded-xl bg-[#070B12] text-center text-xs text-slate-400">
                  No confirmed trade setup. Confluence filters active.
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
