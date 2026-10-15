import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import {
  IndexSymbol,
  SignalData,
  MarketRow,
  SystemDiagnostics,
  PaperTrade,
} from '../types/market';
import { apiService, INDEX_CONFIG } from '../services/api';

interface TradingContextType {
  selectedIndex: IndexSymbol;
  activeTab: string;
  drawerOpen: boolean;
  market: Record<string, MarketRow>;
  signals: Record<string, SignalData>;
  isLive: boolean;
  isRefreshing: boolean;
  lastUpdated: string;
  marketStatus: { equityOpen: boolean; istTime: string };
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
  setActiveTab: (tab: string) => void;
  toggleDrawer: () => void;
  setDrawerOpen: (open: boolean) => void;
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export const TradingProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [selectedIndex, setSelectedIndex] = useState<IndexSymbol>('NIFTY');
  const [activeTab, setActiveTab] = useState<string>('Dashboard');
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  const [market, setMarket] = useState<Record<string, MarketRow>>({});
  const [signals, setSignals] = useState<Record<string, SignalData>>({});
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
    if (!saved) return [];
    try {
      const parsed = JSON.parse(saved);
      if (!Array.isArray(parsed)) return [];
      // Remove the exact hard-coded demo position from older app versions; preserve real user trades.
      return parsed.filter((trade: PaperTrade) => !(
        trade?.id === 'PT-10492' &&
        trade?.option_name === 'NIFTY 24900 CE' &&
        trade?.entry_price === 138.50
      ));
    } catch {
      return [];
    }
  });

  // Save paper trading to localStorage
  useEffect(() => {
    localStorage.setItem('fresh_paper_balance', paperBalance.toString());
  }, [paperBalance, market]);

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
      setIsLive(data.isLive);
      setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      setMarketStatus(apiService.getMarketOpenStatus());

      // Mark open positions only from a fresh, broker-validated option LTP.
      // Underlying spot movement is not a valid substitute for option premium.
      setPaperTrades(prev => prev.map(trade => {
        if (trade.status !== 'OPEN') return trade;
        if (!data.isLive || trade.action !== 'BUY') {
          return { ...trade, mark_status: 'UNAVAILABLE' };
        }
        const currentMkt = data.market[trade.symbol];
        const timestampMs = currentMkt?.timestamp ? Date.parse(currentMkt.timestamp) : Number.NaN;
        const ageMs = Date.now() - timestampMs;
        if (
          !currentMkt ||
          currentMkt.live !== true ||
          !Number.isFinite(timestampMs) ||
          ageMs < 0 ||
          ageMs > 120000
        ) {
          return { ...trade, mark_status: 'UNAVAILABLE' };
        }
        const strikeMatch = trade.option_name.match(/(\d+(?:\.\d+)?)(?=\s*(?:CE|PE)\b)/i);
        if (!strikeMatch) return { ...trade, mark_status: 'UNAVAILABLE' };
        const strike = Number(strikeMatch[1]);
        const quote = currentMkt.option_chain?.find(row => Math.abs(row.strike - strike) < 0.01);
        const optionPrice = trade.side === 'CE' ? quote?.ce_ltp : quote?.pe_ltp;
        if (typeof optionPrice !== 'number' || !Number.isFinite(optionPrice) || optionPrice <= 0) {
          return { ...trade, mark_status: 'UNAVAILABLE' };
        }
        const pnl = Number(((optionPrice - trade.entry_price) * trade.quantity).toFixed(2));
        const pnl_percent = trade.entry_price > 0
          ? Number(((optionPrice - trade.entry_price) / trade.entry_price * 100).toFixed(2))
          : 0;
        return {
          ...trade,
          current_price: optionPrice,
          pnl,
          pnl_percent,
          mark_status: 'LIVE_OPTION_QUOTE',
          mark_timestamp: currentMkt.timestamp,
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
    if (trade.action !== 'BUY') {
      alert('SELL option paper trades are disabled until a short-option margin model is implemented.');
      return;
    }
    if (!Number.isFinite(trade.entry_price) || trade.entry_price <= 0 || trade.lots <= 0) {
      alert('Entry price and lot quantity must be valid positive values.');
      return;
    }
    const currentMkt = market[trade.symbol as IndexSymbol];
    const timestampMs = currentMkt?.timestamp ? Date.parse(currentMkt.timestamp) : Number.NaN;
    const ageMs = Date.now() - timestampMs;
    if (
      !currentMkt ||
      currentMkt.live !== true ||
      !Number.isFinite(timestampMs) ||
      ageMs < 0 ||
      ageMs > 120000
    ) {
      alert('Paper order blocked: no fresh live market snapshot is available.');
      return;
    }
    const strikeMatch = trade.option_name.match(/(\\d+(?:\\.\\d+)?)(?=\\s*(?:CE|PE)\\b)/i);
    if (!strikeMatch) {
      alert('Paper order blocked: option strike could not be matched to a broker quote.');
      return;
    }
    const strike = Number(strikeMatch[1]);
    const quote = currentMkt.option_chain?.find(row => Math.abs(row.strike - strike) < 0.01);
    const actualPrice = trade.side === 'CE' ? quote?.ce_ltp : quote?.pe_ltp;
    if (typeof actualPrice !== 'number' || !Number.isFinite(actualPrice) || actualPrice <= 0) {
      alert('Paper order blocked: no verified option LTP is available for this strike.');
      return;
    }
    if (Math.abs(actualPrice - trade.entry_price) > Math.max(1, actualPrice * 0.02)) {
      alert('Option price changed by more than 2%. Refresh the option chain and place the paper order again.');
      return;
    }
    const lotSize = INDEX_CONFIG[trade.symbol as IndexSymbol]?.lotSize || 50;
    const quantity = trade.lots * lotSize;
    const entryPrice = actualPrice;
    const requiredMargin = entryPrice * quantity;

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
      entry_price: entryPrice,
      current_price: entryPrice,
      stop_loss: trade.stop_loss,
      target: trade.target,
      pnl: 0,
      pnl_percent: 0,
      status: 'OPEN',
      mark_status: 'LIVE_OPTION_QUOTE',
      mark_timestamp: currentMkt.timestamp,
    };

    setPaperBalance(prev => prev - requiredMargin);
    setPaperTrades(prev => [newTrade, ...prev]);
  }, [paperBalance]);

  const closePaperTrade = useCallback((id: string) => {
    const trade = paperTrades.find(item => item.id === id && item.status === 'OPEN');
    if (!trade) return;
    const markTime = trade.mark_timestamp ? Date.parse(trade.mark_timestamp) : Number.NaN;
    const markAge = Date.now() - markTime;
    if (
      trade.action !== 'BUY' ||
      trade.mark_status !== 'LIVE_OPTION_QUOTE' ||
      !Number.isFinite(markTime) ||
      markAge < 0 ||
      markAge > 120000
    ) {
      alert('Square-off blocked: a fresh verified option LTP is not available. No estimated exit price was used.');
      return;
    }
    const exitPrice = trade.current_price;
    const pnl = Number(((exitPrice - trade.entry_price) * trade.quantity).toFixed(2));
    const pnl_percent = trade.entry_price > 0
      ? Number(((exitPrice - trade.entry_price) / trade.entry_price * 100).toFixed(2))
      : 0;
    setPaperBalance(balance => balance + exitPrice * trade.quantity);
    setPaperTrades(prev => prev.map(item => item.id === id && item.status === 'OPEN' ? {
      ...item,
      status: 'CLOSED',
      closed_at: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
      exit_price: exitPrice,
      current_price: exitPrice,
      pnl,
      pnl_percent,
      mark_status: 'LIVE_OPTION_QUOTE',
    } : item));
  }, [paperTrades]);

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
        activeTab,
        drawerOpen,
        market,
        signals,
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
