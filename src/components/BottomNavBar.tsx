import React from 'react';
import {
  LayoutDashboard,
  TrendingUp,
  Table2,
  Zap,
  Layers,
  Wallet,
  Settings,
} from 'lucide-react';
import { useTrading } from '../context/TradingContext';

export const BottomNavBar: React.FC = () => {
  const { activeTab, setActiveTab, signals } = useTrading();

  // Count confirmed or confirming actionable signals
  const activeSignalsCount = Object.values(signals).filter(
    s => s.decision === 'CALL BUY' || s.decision === 'PUT BUY' || s.candidate_decision === 'CALL BUY' || s.candidate_decision === 'PUT BUY'
  ).length;

  const navItems = [
    { id: 'Dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'Signals', label: 'Signals', icon: Zap, badge: activeSignalsCount },
    { id: 'Option Chain', label: 'Chain', icon: Table2 },
    { id: 'Paper Trading', label: 'Broker', icon: Wallet },
    { id: '5-Layer Quant', label: 'Quant', icon: Layers },
    { id: 'Settings', label: 'Settings', icon: Settings },
  ];

  return (
    <nav className="w-full bg-[#0E1524] border-t border-[#1C2740] px-2 py-1.5 flex items-center justify-around sticky bottom-0 z-40 select-none pb-safe">
      {navItems.map(item => {
        const Icon = item.icon;
        const isActive = activeTab === item.id;

        return (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={`relative flex flex-col items-center justify-center py-1 px-3 rounded-xl transition-all duration-150 ${
              isActive
                ? 'text-cyan-400 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <div className="relative">
              <Icon className={`w-5 h-5 transition-transform duration-150 ${isActive ? 'scale-110 text-cyan-400' : ''}`} />
              {item.badge !== undefined && item.badge > 0 && (
                <span className="absolute -top-1 -right-2 px-1 min-w-[14px] h-[14px] flex items-center justify-center bg-cyan-500 text-[#070B12] text-[9px] font-black rounded-full font-mono">
                  {item.badge}
                </span>
              )}
            </div>
            <span className="text-[10px] mt-1 font-medium tracking-tight">
              {item.label}
            </span>
            {isActive && (
              <span className="w-4 h-0.5 bg-cyan-400 rounded-full mt-0.5"></span>
            )}
          </button>
        );
      })}
    </nav>
  );
};
