import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import {
  IndexSymbol,
  CommoditySymbol,
  SignalData,
  MarketRow,
  CommodityRow,
  SystemDiagnostics,
  PaperTrade,
} from '../types/market';
import { apiService, INDEX_CONFIG } from '../services/api';

interface TradingContextType {
  selectedIndex: IndexSymbol;
  selectedCommodity: CommoditySymbol;
  activeTab: string;
  drawerOpen: boolean;
  market: Record<string, MarketRow>;
  signals: Record<string, SignalData>;
  commodities: CommodityRow[];
  isLive: boolean;
  isRefreshing: boolean;
  lastUpdated: string;
  marketStatus: { equityOpen: boolean; mcxOpen: boolean; istTime: string };
  diagnostics: SystemDiagnostics | null;
  paperBalance: number;
  paperTrades: PaperTrade[];
  executePaperTrade: (trade: {
    symbol: string;
    option_name: string;
    side: 'CE' | 'PE';
    action: 'BUY' | 'SELL';
    lots: number;
    entry_price: number;
    stop_loss: number;
    target: number;
  }) => void;
  closePaperTrade: (id: string) => void;
  resetPaperAccount: () => void;
  refresh: () => Promise<void>;
  setSelectedIndex: (idx: IndexSymbol) => void;
  setSelectedCommodity: (comm: CommoditySymbol) => void;
  setActiveTab: (tab: string) => void;
  toggleDrawer: () => void;
  setDrawerOpen: (open: boolean) => void;
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export const TradingProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [selectedIndex, setSelectedIndex] = useState<IndexSymbol>('NIFTY');
  const [selectedCommodity, setSelectedCommodity] = useState<CommoditySymbol>('CRUDEOIL');
  const [activeTab, setActiveTab] = useState<string>('Dashboard');
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  const [market, setMarket] = useState<Record<string, MarketRow>>({});
  const [signals, setSignals] = useState<Record<string, SignalData>>({});
  const [commodities, setCommodities] = useState<CommodityRow[]>([]);
  const [isLive, setIsLive] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [marketStatus, setMarketStatus] = useState(apiService.getMarketOpenStatus());
  const [diagnostics, setDiagnostics] = useState<SystemDiagnostics | null>(null);

  // Paper Trading state persisted in localStorage
  const [paperBalance, setPaperBalance] = useState<number>(() => {
    const saved = localStorage.getItem('fresh_paper_balance');
    return saved ? parseFloat(saved) : 1000000;
  });

  const [paperTrades, setPaperTrades] = useState<PaperTrade[]>(() => {
    const saved = localStorage.getItem('fresh_paper_trades');
    return saved ? JSON.parse(saved) : [
      {
        id: 'PT-10492',
        timestamp: new Date(Date.now() - 3600000 * 2).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
        symbol: 'NIFTY',
        option_name: 'NIFTY 24900 CE',
        side: 'CE',
        action: 'BUY',
        lots: 2,
        quantity: 150,
        entry_price: 138.50,
        current_price: 162.20,
        stop_loss: 112.00,
        target: 205.00,
        pnl: 3555.00,
        pnl_percent: 17.11,
        status: 'OPEN',
      },
    ];
  });

  // Save paper trading to localStorage
  useEffect(() => {
    localStorage.setItem('fresh_paper_balance', paperBalance.toString());
  }, [paperBalance]);

  useEffect(() => {
    localStorage.setItem('fresh_paper_trades', JSON.stringify(paperTrades));
  }, [paperTrades]);

  // Main refresh routine
  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const data = await apiService.fetchSignals();
      setMarket(data.market);
      setSignals(data.signals);
      setCommodities(data.commodities);
      setIsLive(data.isLive);
      setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      setMarketStatus(apiService.getMarketOpenStatus());

      // Update P&L on open paper trades based on latest market prices
      setPaperTrades(prev => prev.map(trade => {
        if (trade.status !== 'OPEN') return trade;
        const currentMkt = data.market[trade.symbol];
        if (!currentMkt) return trade;

        // Approximate option current price movement with spot delta ~ 0.5
        const spotDiff = currentMkt.ltp - currentMkt.open;
        const estOptionPrice = Math.max(5, Number((trade.entry_price + (trade.side === 'CE' ? spotDiff * 0.45 : -spotDiff * 0.45)).toFixed(2)));
        const pnl = Number(((estOptionPrice - trade.entry_price) * trade.quantity).toFixed(2));
        const pnl_percent = Number(((estOptionPrice - trade.entry_price) / trade.entry_price * 100).toFixed(2));

        return {
          ...trade,
          current_price: estOptionPrice,
          pnl,
          pnl_percent,
        };
      }));

      // Fetch diagnostics async
      apiService.getDiagnostics().then(d => setDiagnostics(d));
    } catch (e) {
      console.error('Refresh error:', e);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  // Paper Trade execution
  const executePaperTrade = useCallback((trade: {
    symbol: string;
    option_name: string;
    side: 'CE' | 'PE';
    action: 'BUY' | 'SELL';
    lots: number;
    entry_price: number;
    stop_loss: number;
    target: number;
  }) => {
    const lotSize = INDEX_CONFIG[trade.symbol as IndexSymbol]?.lotSize || 50;
    const quantity = trade.lots * lotSize;
    const requiredMargin = trade.entry_price * quantity;

    if (requiredMargin > paperBalance) {
      alert(`Insufficient margin! Required ₹${requiredMargin.toLocaleString('en-IN')} but available is ₹${paperBalance.toLocaleString('en-IN')}`);
      return;
    }

    const newTrade: PaperTrade = {
      id: `PT-${Math.floor(10000 + Math.random() * 90000)}`,
      timestamp: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
      symbol: trade.symbol,
      option_name: trade.option_name,
      side: trade.side,
      action: trade.action,
      lots: trade.lots,
      quantity,
      entry_price: trade.entry_price,
      current_price: trade.entry_price,
      stop_loss: trade.stop_loss,
      target: trade.target,
      pnl: 0,
      pnl_percent: 0,
      status: 'OPEN',
    };

    setPaperBalance(prev => prev - requiredMargin);
    setPaperTrades(prev => [newTrade, ...prev]);
  }, [paperBalance]);

  const closePaperTrade = useCallback((id: string) => {
    setPaperTrades(prev => prev.map(trade => {
      if (trade.id === id && trade.status === 'OPEN') {
        const exitMargin = trade.current_price * trade.quantity;
        setPaperBalance(bal => bal + exitMargin);
        return {
          ...trade,
          status: 'CLOSED',
          closed_at: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
          exit_price: trade.current_price,
        };
      }
      return trade;
    }));
  }, []);

  const resetPaperAccount = useCallback(() => {
    setPaperBalance(1000000);
    setPaperTrades([]);
  }, []);

  const toggleDrawer = useCallback(() => {
    setDrawerOpen(prev => !prev);
  }, []);

  // Periodic polling every 5 seconds (matching Android app)
  useEffect(() => {
    refresh();
    const interval = setInterval(() => {
      // only refresh if tab is visible
      if (!document.hidden) {
        refresh();
      }
    }, 5000);

    const handleVisibilityChange = () => {
      if (!document.hidden) {
        refresh();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [refresh]);

  return (
    <TradingContext.Provider
      value={{
        selectedIndex,
        selectedCommodity,
        activeTab,
        drawerOpen,
        market,
        signals,
        commodities,
        isLive,
        isRefreshing,
        lastUpdated,
        marketStatus,
        diagnostics,
        paperBalance,
        paperTrades,
        executePaperTrade,
        closePaperTrade,
        resetPaperAccount,
        refresh,
        setSelectedIndex,
        setSelectedCommodity,
        setActiveTab,
        toggleDrawer,
        setDrawerOpen,
      }}
    >
      {children}
    </TradingContext.Provider>
  );
};

export const useTrading = (): TradingContextType => {
  const context = useContext(TradingContext);
  if (!context) {
    throw new Error('useTrading must be used within a TradingProvider');
  }
  return context;
};
