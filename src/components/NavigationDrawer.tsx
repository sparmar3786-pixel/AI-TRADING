import React from 'react';
import {
  X, LayoutDashboard, TrendingUp, Table2, BarChart3, Sliders, Zap,
  ShieldAlert, Activity, Cpu, Wallet, Settings, History, FileSpreadsheet,
} from 'lucide-react';
import { useTrading } from '../context/TradingContext';

export const NavigationDrawer: React.FC = () => {
  const { drawerOpen, setDrawerOpen, activeTab, setActiveTab, isLive, marketStatus } = useTrading();
  if (!drawerOpen) return null;

  const handleSelectTab = (tabId: string) => {
    setActiveTab(tabId);
    setDrawerOpen(false);
  };

  const sections = [
    { title: 'MARKET & INSTRUMENTS', items: [
      { id: 'Dashboard', label: 'Dashboard Overview', icon: LayoutDashboard },
      { id: 'Market', label: 'Spot & Market Depth', icon: TrendingUp },
      { id: 'Option Chain', label: 'Option Chain & Greeks', icon: Table2 },
      { id: 'OI Lab', label: 'OI Lab & PCR Analysis', icon: BarChart3 },
      { id: 'Indicators', label: 'Technical Indicators', icon: Sliders },
    ]},
    { title: 'ALGO SIGNALS & QUANT', items: [
      { id: 'Signals', label: 'Live Signals (10m Gate)', icon: Zap },
      { id: '5-Layer Quant', label: '5-Layer Quant Engine', icon: Activity },
      { id: 'Strategy Library', label: 'Strategy Library', icon: FileSpreadsheet },
    ]},
    { title: 'EXECUTION & SIMULATION', items: [
      { id: 'Paper Trading', label: 'Broker Home (Paper)', icon: Wallet },
      { id: 'Risk Calculator', label: 'Risk & Position Sizing', icon: ShieldAlert },
      { id: 'Backtesting', label: 'Quant Backtester', icon: History },
    ]},
    { title: 'SYSTEM & SETTINGS', items: [
      { id: 'Settings', label: 'Settings & API Configuration', icon: Settings },
      { id: 'Data Health', label: 'Data Health & Diagnostics', icon: Cpu },
    ]},
  ];

  return (
    <div className="fixed inset-0 z-50 flex select-none">
      <div className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity" onClick={() => setDrawerOpen(false)} />
      <div className="relative w-80 max-w-[85vw] h-full bg-[#0E1524] border-r border-[#1C2740] flex flex-col z-10 shadow-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-[#1C2740] bg-[#070B12] flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20"><Zap className="w-6 h-6 text-[#070B12] fill-current" /></div>
            <div><div className="text-white font-black text-sm tracking-widest font-mono">QUANT TRADING</div><div className="text-cyan-400 text-[11px] font-semibold tracking-wide">DETERMINISTIC TERMINAL</div></div>
          </div>
          <button onClick={() => setDrawerOpen(false)} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-[#17223B]"><X className="w-5 h-5" /></button>
        </div>
        <div className="px-4 py-2.5 bg-[#121A2D] border-b border-[#1C2740] flex items-center justify-between text-xs">
          <div className="flex items-center space-x-1.5"><span className={`w-2 h-2 rounded-full ${isLive ? 'bg-emerald-400 animate-live-blink' : 'bg-amber-400'}`}></span><span className="text-slate-300 font-medium">{isLive ? 'Live Broker Feed' : 'Local Fallback'}</span></div>
          <span className="text-[11px] text-cyan-400 font-mono">{marketStatus.istTime}</span>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
          {sections.map(sec => <div key={sec.title}>
            <div className="text-[10px] font-black text-slate-500 uppercase tracking-widest px-3 mb-1.5">{sec.title}</div>
            <div className="space-y-0.5">{sec.items.map(item => { const Icon = item.icon; const isSelected = activeTab === item.id; return (
              <button key={item.id} onClick={() => handleSelectTab(item.id)} className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-left transition-all text-xs font-semibold ${isSelected ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 font-bold' : 'text-slate-300 hover:bg-[#17223B] hover:text-white'}`}>
                <Icon className={`w-4 h-4 flex-shrink-0 ${isSelected ? 'text-cyan-400' : 'text-slate-400'}`} /><span className="truncate">{item.label}</span>
              </button>
            );})}</div>
          </div>)}
        </div>
        <div className="p-3 bg-[#070B12] border-t border-[#1C2740] text-[10px] text-slate-500 text-center font-mono">QUANT TRADING TERMINAL • RAILWAY CONNECTED</div>
      </div>
    </div>
  );
};
