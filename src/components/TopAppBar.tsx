import React from 'react';
import { Menu, RefreshCw, Zap, Settings, BrainCircuit } from 'lucide-react';
import { useTrading } from '../context/TradingContext';

export const TopAppBar: React.FC = () => {
  const { isLive, isRefreshing, refresh, toggleDrawer, marketStatus, activeTab, setActiveTab } = useTrading();

  const getStatusBadge = () => {
    if (!isLive) {
      return (
        <div className="flex items-center space-x-1 px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-400 text-[11px] font-semibold">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
          <span>OFFLINE SIM</span>
        </div>
      );
    }
    if (marketStatus.equityOpen) {
      return (
        <div className="flex items-center space-x-1 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[11px] font-semibold">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-live-blink"></span>
          <span>API LIVE</span>
        </div>
      );
    }
    return (
      <div className="flex items-center space-x-1 px-2 py-0.5 rounded-full bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 text-[11px] font-semibold">
        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
        <span>CONNECTED</span>
      </div>
    );
  };

  return (
    <header className="w-full bg-[#0E1524] border-b border-[#1C2740] px-4 py-2.5 flex items-center justify-between sticky top-0 z-40 select-none shadow-md">
      <div className="flex items-center space-x-3">
        <button
          onClick={toggleDrawer}
          className="p-2 -ml-1 rounded-xl text-slate-300 hover:text-white hover:bg-[#17223B] active:scale-95 transition-all"
          title="Open Navigation Drawer"
          aria-label="Navigation Menu"
        >
          <Menu className="w-5 h-5 text-cyan-400" />
        </button>

        <div>
          <div className="flex items-center space-x-1.5">
            <span className="text-white font-black text-sm tracking-widest font-mono">FRESH</span>
            <span className="px-1.5 py-0.2 bg-cyan-400/20 text-cyan-400 text-[10px] font-bold rounded font-mono">AI</span>
          </div>
          <div className="text-[10px] text-slate-400 font-semibold tracking-wider uppercase">
            {activeTab}
          </div>
        </div>
      </div>

      <div className="flex items-center space-x-2">
        {getStatusBadge()}

        <button
          onClick={() => refresh()}
          disabled={isRefreshing}
          className={`p-2 rounded-xl text-slate-400 hover:text-cyan-400 hover:bg-[#17223B] transition-all active:scale-90 ${
            isRefreshing ? 'animate-spin text-cyan-400' : ''
          }`}
          title="Refresh market feed"
          aria-label="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </button>

        <button
          onClick={() => setActiveTab('Market Intelligence')}
          className={`p-2 rounded-xl transition-all active:scale-90 flex items-center justify-center ${
            activeTab === 'Market Intelligence'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 shadow-sm shadow-cyan-500/20'
              : 'text-slate-400 hover:text-cyan-400 hover:bg-[#17223B]'
          }`}
          title="NVIDIA AI Market Intelligence (एआई सेक्शन)"
          aria-label="AI Intelligence"
        >
          <BrainCircuit className="w-4 h-4" />
        </button>

        <button
          onClick={() => setActiveTab('Settings')}
          className={`p-2 rounded-xl transition-all active:scale-90 flex items-center justify-center ${
            activeTab === 'Settings'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 shadow-sm shadow-cyan-500/20'
              : 'text-slate-400 hover:text-cyan-400 hover:bg-[#17223B]'
          }`}
          title="Settings & API Keys (सेटिंग्स)"
          aria-label="Settings"
        >
          <Settings className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
