import React from 'react';
import {
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  Zap,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Layers,
  ArrowRight,
  Wallet,
  Settings,
  Key,
} from 'lucide-react';
import { useTrading } from '../context/TradingContext';
import { INDEX_CONFIG } from '../services/api';

export const DashboardPage: React.FC = () => {
  const {
    selectedIndex,
    market,
    signals,
    setActiveTab,
    executePaperTrade,
  } = useTrading();

  const currentMarket = market[selectedIndex];
  const currentSignal = signals[selectedIndex];
  const cfg = INDEX_CONFIG[selectedIndex];

  const ltp = currentMarket ? currentMarket.ltp : cfg.basePrice;
  const change = currentMarket ? currentMarket.change : 0;
  const changePercent = currentMarket ? currentMarket.change_percent : 0;
  const isPositive = change >= 0;

  // Stability gate calculation
  const stability = currentSignal?.signal_stability;
  const isConfirming = stability?.state === 'CONFIRMING';
  const isConfirmed = stability?.state === 'CONFIRMED';
  const remainingSecs = stability?.remaining_seconds ?? 0;
  const elapsedSecs = stability?.elapsed_seconds ?? 0;
  const percentDone = Math.min(100, Math.floor((elapsedSecs / 600) * 100));

  const handleQuickPaperTrade = () => {
    const strikeStep = cfg.strikeStep;
    const atmStrike = Math.round(ltp / strikeStep) * strikeStep;
    const strike = currentSignal?.strike || atmStrike;
    const side = currentSignal?.option_side || (isPositive ? 'CE' : 'PE');
    const entryPrice = currentSignal?.entry || 145;

    executePaperTrade({
      symbol: selectedIndex,
      option_name: `${selectedIndex} ${strike} ${side}`,
      side: side,
      action: 'BUY',
      lots: 2,
      entry_price: entryPrice,
      stop_loss: currentSignal?.stop_loss || Number((entryPrice * 0.8).toFixed(1)),
      target: currentSignal?.target || Number((entryPrice * 1.4).toFixed(1)),
    });
    setActiveTab('Paper Trading');
  };

  return (
    <div className="p-3 pb-8 space-y-3.5 select-none max-w-2xl mx-auto">
      {/* Settings & Auto Keys Quick-Access Bar */}
      <div
        onClick={() => setActiveTab('Settings')}
        className="p-2.5 rounded-xl bg-gradient-to-r from-cyan-950/60 to-[#121A2D] border border-cyan-500/30 flex items-center justify-between cursor-pointer hover:border-cyan-400 active:scale-98 transition-all shadow-md"
      >
        <div className="flex items-center space-x-2">
          <div className="p-1.5 rounded-lg bg-cyan-500/20 text-cyan-400">
            <Settings className="w-4 h-4 animate-spin-slow" />
          </div>
          <div>
            <div className="text-xs font-bold text-white flex items-center space-x-1.5">
              <span>Settings & 1-Click Keys (सेटिंग्स)</span>
              <span className="px-1.5 py-0.2 bg-emerald-500/20 text-emerald-400 text-[9px] font-mono rounded">Active</span>
            </div>
            <div className="text-[10px] text-slate-400">
              API Keys, Firebase, Stop-Loss व Trading Settings प्रबंधित करें
            </div>
          </div>
        </div>
        <div className="flex items-center space-x-1 text-cyan-400 text-xs font-bold font-mono pl-2">
          <span>OPEN</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </div>
      </div>

      {/* 1. Main Spot Price Card */}
      <div className="card-base p-4 border border-[#1C2740] bg-gradient-to-b from-[#121A2D] to-[#0E1524] relative overflow-hidden shadow-lg">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-black tracking-widest text-cyan-400 font-mono">
                {selectedIndex}
              </span>
              <span className="text-[10px] text-slate-400 font-semibold">
                {cfg.name}
              </span>
            </div>
            <div className="text-2xl font-black text-white font-mono mt-1 tracking-tight">
              ₹{ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>

          <div className="text-right">
            <div
              className={`inline-flex items-center space-x-1 px-2.5 py-1 rounded-xl text-xs font-bold font-mono ${
                isPositive ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
              }`}
            >
              {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
              <span>{isPositive ? '+' : ''}{change.toFixed(2)} ({isPositive ? '+' : ''}{changePercent.toFixed(2)}%)</span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono mt-1">
              India VIX: <span className="text-amber-300 font-bold">{currentMarket?.india_vix || 13.85}</span>
            </div>
          </div>
        </div>

        {/* Range bar: Day Low to Day High */}
        <div className="mt-3.5 pt-3 border-t border-[#1C2740]/80">
          <div className="flex justify-between text-[10px] text-slate-400 font-mono mb-1">
            <span>Low: ₹{currentMarket?.low.toLocaleString('en-IN')}</span>
            <span className="text-cyan-400 font-semibold">VWAP: ₹{currentMarket?.vwap.toLocaleString('en-IN')}</span>
            <span>High: ₹{currentMarket?.high.toLocaleString('en-IN')}</span>
          </div>
          <div className="w-full h-1.5 bg-[#070B12] rounded-full overflow-hidden relative">
            <div
              className="h-full bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-400 rounded-full"
              style={{
                width: `${Math.min(
                  100,
                  Math.max(
                    5,
                    (((ltp - (currentMarket?.low || ltp * 0.99)) /
                      ((currentMarket?.high || ltp * 1.01) - (currentMarket?.low || ltp * 0.99))) *
                      100) || 50
                  )
                )}%`,
              }}
            ></div>
          </div>
        </div>
      </div>

      {/* 2. 10-Minute Signal Stability Gate Card */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#101726]">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center space-x-2">
            <Clock className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-black tracking-wide text-white uppercase font-mono">
              10-Minute Stability Gate
            </span>
          </div>

          {isConfirmed ? (
            <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[10px] font-bold">
              <CheckCircle2 className="w-3 h-3" />
              <span>ACTIONABLE CONFIRMED</span>
            </span>
          ) : isConfirming ? (
            <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-400 text-[10px] font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
              <span>CONFIRMING ({600 - elapsedSecs}s)</span>
            </span>
          ) : (
            <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-slate-700/30 text-slate-400 text-[10px] font-semibold">
              <span>STANDBY / WAIT</span>
            </span>
          )}
        </div>

        {/* Candidate Signal Box */}
        {currentSignal?.candidate_decision && currentSignal.candidate_decision !== 'WAIT' ? (
          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span
                  className={`px-2 py-0.5 rounded-md text-xs font-black font-mono ${
                    currentSignal.candidate_decision === 'CALL BUY'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                      : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                  }`}
                >
                  {currentSignal.candidate_decision}
                </span>
                <span className="text-xs font-bold text-white font-mono">
                  {currentSignal.strike} {currentSignal.option_side}
                </span>
              </div>

              <div className="text-right">
                <span className="text-[10px] text-slate-400">Risk : Reward</span>
                <div className="text-xs font-bold text-cyan-400 font-mono">
                  {currentSignal.risk_reward || '1 : 2.0'}
                </div>
              </div>
            </div>

            {/* Entry, SL, Target metrics */}
            <div className="grid grid-cols-3 gap-2 pt-1 text-center font-mono">
              <div className="p-1.5 rounded-lg bg-[#0E1524]">
                <div className="text-[9px] text-slate-400">ENTRY LTP</div>
                <div className="text-xs font-bold text-slate-100">₹{currentSignal.entry}</div>
              </div>
              <div className="p-1.5 rounded-lg bg-[#0E1524]">
                <div className="text-[9px] text-rose-400">STOP LOSS</div>
                <div className="text-xs font-bold text-rose-300">₹{currentSignal.stop_loss}</div>
              </div>
              <div className="p-1.5 rounded-lg bg-[#0E1524]">
                <div className="text-[9px] text-emerald-400">TARGET</div>
                <div className="text-xs font-bold text-emerald-300">₹{currentSignal.target}</div>
              </div>
            </div>

            {/* Stability Progress bar */}
            <div className="space-y-1 pt-1">
              <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                <span>Confirmation window</span>
                <span className="text-cyan-400 font-semibold">{elapsedSecs}s / 600s ({percentDone}%)</span>
              </div>
              <div className="w-full h-1.5 bg-[#0E1524] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full transition-all duration-300"
                  style={{ width: `${percentDone}%` }}
                ></div>
              </div>
            </div>

            {/* Quick Action Button */}
            <div className="pt-1 flex items-center space-x-2">
              <button
                onClick={handleQuickPaperTrade}
                className="flex-1 py-2 px-3 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-[#070B12] font-black text-xs flex items-center justify-center space-x-1.5 shadow-md shadow-cyan-500/20 active:scale-95 transition-all"
              >
                <Wallet className="w-3.5 h-3.5" />
                <span>EXECUTE IN PAPER BROKER</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] text-center space-y-1">
            <div className="text-xs text-slate-300 font-medium">
              Market in consolidation • Waiting for high-probability 5-layer confluence
            </div>
            <div className="text-[10px] text-slate-500">
              Guards active: ADX & Spread within limits • 10-minute confirmation armed
            </div>
          </div>
        )}
      </div>

      {/* 3. Market Pulse & Options Flow Grid */}
      <div className="grid grid-cols-2 gap-3">
        {/* Put-Call Ratio Card */}
        <div
          onClick={() => setActiveTab('OI Lab')}
          className="card-base card-hover p-3.5 border border-[#1C2740] cursor-pointer"
        >
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span className="font-semibold">Put-Call Ratio (PCR)</span>
            <ArrowRight className="w-3 h-3 text-cyan-400" />
          </div>
          <div className="text-xl font-black text-white font-mono">
            {currentMarket?.pcr || 1.15}
          </div>
          <div className="text-[10px] text-emerald-400 font-semibold mt-1">
            {currentMarket && currentMarket.pcr >= 1.0 ? 'Bullish Put Writing Floor' : 'Bearish Call Resistance'}
          </div>
        </div>

        {/* Max Pain Strike Card */}
        <div
          onClick={() => setActiveTab('Option Chain')}
          className="card-base card-hover p-3.5 border border-[#1C2740] cursor-pointer"
        >
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span className="font-semibold">Max Pain Strike</span>
            <ArrowRight className="w-3 h-3 text-cyan-400" />
          </div>
          <div className="text-xl font-black text-cyan-400 font-mono">
            {currentMarket?.max_pain || Math.round(ltp / cfg.strikeStep) * cfg.strikeStep}
          </div>
          <div className="text-[10px] text-slate-400 font-medium mt-1">
            Target expiry gravitational center
          </div>
        </div>
      </div>

      {/* 4. Module Fast Launchers */}
      <div className="space-y-2 pt-1">
        <div className="text-[11px] font-black text-slate-400 tracking-wider uppercase font-mono">
          TRADING ENGINES & WORKSPACE
        </div>

        <div className="grid grid-cols-2 gap-2.5">
          <button
            onClick={() => setActiveTab('5-Layer Quant')}
            className="card-base card-hover p-3 border border-[#1C2740] flex items-center space-x-2.5 text-left transition-all"
          >
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="text-xs font-bold text-white">5-Layer Quant</div>
              <div className="text-[10px] text-slate-400">Confluence engine</div>
            </div>
          </button>


          <button
            onClick={() => setActiveTab('Paper Trading')}
            className="card-base card-hover p-3 border border-[#1C2740] flex items-center space-x-2.5 text-left transition-all"
          >
            <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
              <Wallet className="w-5 h-5" />
            </div>
            <div>
              <div className="text-xs font-bold text-white">Paper Broker</div>
              <div className="text-[10px] text-slate-400">₹10 Lakhs Virtual</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
};
