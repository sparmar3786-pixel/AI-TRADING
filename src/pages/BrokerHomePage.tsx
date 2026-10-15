import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { INDEX_CONFIG } from '../services/api';
import { IndexSymbol } from '../types/market';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  RotateCcw,
  PlusCircle,
  XCircle,
  ShieldCheck,
  CheckCircle,
} from 'lucide-react';

export const BrokerHomePage: React.FC = () => {
  const {
    paperBalance,
    paperTrades,
    closePaperTrade,
    executePaperTrade,
    resetPaperAccount,
    selectedIndex,
    market,
  } = useTrading();

  const [orderModalOpen, setOrderModalOpen] = useState(false);
  const [orderSymbol, setOrderSymbol] = useState<IndexSymbol>(selectedIndex);
  const [orderSide, setOrderSide] = useState<'CE' | 'PE'>('CE');
  const [orderLots, setOrderLots] = useState(2);
  const [orderPrice, setOrderPrice] = useState(150);

  React.useEffect(() => {
    const cfg = INDEX_CONFIG[orderSymbol];
    const mkt = market[orderSymbol];
    if (mkt && cfg) {
      const spot = mkt.ltp || cfg.basePrice;
      const strike = Math.round(spot / cfg.strikeStep) * cfg.strikeStep;
      const quote = mkt.option_chain?.find(r => Math.abs(r.strike - strike) < 0.01);
      const estPrice = quote ? (orderSide === 'CE' ? quote.ce_ltp : quote.pe_ltp) : 145;
      if (estPrice > 0) setOrderPrice(estPrice);
    }
  }, [orderSymbol, orderSide, market]);

  const openTrades = paperTrades.filter(t => t.status === 'OPEN');
  const closedTrades = paperTrades.filter(t => t.status === 'CLOSED');

  // Total M2M P&L
  const totalM2M = openTrades.reduce((acc, t) => acc + t.pnl, 0);
  const realizedPnl = closedTrades.reduce((acc, t) => acc + (t.pnl || 0), 0);

  const handlePlaceOrder = (e: React.FormEvent) => {
    e.preventDefault();
    const cfg = INDEX_CONFIG[orderSymbol];
    const mkt = market[orderSymbol];
    const spot = mkt?.ltp || cfg.basePrice;
    const strike = Math.round(spot / cfg.strikeStep) * cfg.strikeStep;

    executePaperTrade({
      symbol: orderSymbol,
      option_name: `${orderSymbol} ${strike} ${orderSide}`,
      side: orderSide,
      action: 'BUY',
      lots: orderLots,
      entry_price: orderPrice,
      stop_loss: Number((orderPrice * 0.8).toFixed(1)),
      target: Number((orderPrice * 1.4).toFixed(1)),
    });
    setOrderModalOpen(false);
  };

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      {/* Account Balance Summary Card */}
      <div className="card-base p-4 border border-[#1C2740] bg-gradient-to-r from-[#121A2D] to-[#0E1524]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-black text-cyan-400 font-mono tracking-wider">
              PAPER TRADING ACCOUNT
            </div>
            <div className="text-2xl font-black text-white font-mono mt-1">
              ₹{paperBalance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              Available Margin Balance
            </div>
          </div>

          <div className="text-right">
            <div
              className={`text-lg font-black font-mono ${
                totalM2M >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {totalM2M >= 0 ? '+' : ''}₹{totalM2M.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              Live M2M Unrealized P&L
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-4 pt-3 border-t border-[#1C2740] flex items-center justify-between">
          <button
            onClick={() => setOrderModalOpen(true)}
            className="py-2 px-4 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#070B12] font-black text-xs font-mono flex items-center space-x-1.5 shadow-md shadow-cyan-500/20 active:scale-95 transition-all"
          >
            <PlusCircle className="w-4 h-4" />
            <span>NEW ORDER</span>
          </button>

          <button
            onClick={resetPaperAccount}
            className="py-1.5 px-3 rounded-xl bg-[#17223B] hover:bg-[#1E2C4D] text-slate-300 font-bold text-xs font-mono flex items-center space-x-1 border border-[#1C2740] active:scale-95 transition-all"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>RESET ACCOUNT</span>
          </button>
        </div>
      </div>

      {/* Active Open Positions */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between px-1">
          <span className="text-xs font-black text-slate-400 uppercase tracking-wider font-mono">
            Active Open Positions ({openTrades.length})
          </span>
          <span className="text-[10px] text-cyan-400 font-mono">
            Verified option LTP only
          </span>
        </div>

        {openTrades.length === 0 ? (
          <div className="card-base p-6 border border-[#1C2740] bg-[#101726] text-center text-slate-400 text-xs">
            No open paper positions. Use New Order or tap an option in the Option Chain.
          </div>
        ) : (
          openTrades.map(trade => {
            const markTime = trade.mark_timestamp ? Date.parse(trade.mark_timestamp) : Number.NaN;
            const markAge = Date.now() - markTime;
            const markVerified = trade.mark_status === 'LIVE_OPTION_QUOTE' && Number.isFinite(markTime) && markAge >= 0 && markAge <= 120000;
            const isProfit = markVerified && trade.pnl >= 0;

            return (
              <div
                key={trade.id}
                className="card-base p-3.5 border border-[#1C2740] bg-[#101726] space-y-2.5"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-black text-white font-mono">
                        {trade.option_name}
                      </span>
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${
                          trade.side === 'CE' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                        }`}
                      >
                        {trade.action} {trade.side}
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                      {trade.lots} Lots ({trade.quantity} Qty) • Placed at {trade.timestamp}
                    </div>
                  </div>

                  <div className="text-right">
                    <div
                      className={`text-sm font-black font-mono ${
                        isProfit ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {markVerified ? `${isProfit ? '+' : ''}₹${trade.pnl.toLocaleString('en-IN')}` : 'P&L —'}
                    </div>
                    <div className="text-[10px] font-mono text-slate-400">
                      {markVerified ? `(${isProfit ? '+' : ''}${trade.pnl_percent.toFixed(2)}%)` : 'WAITING FOR VERIFIED OPTION LTP'}
                    </div>
                  </div>
                </div>

                {/* Price Metrics Grid */}
                <div className="grid grid-cols-4 gap-1.5 p-2 rounded-xl bg-[#070B12] text-center font-mono text-xs">
                  <div>
                    <div className="text-[9px] text-slate-500">ENTRY</div>
                    <div className="font-bold text-white">₹{trade.entry_price}</div>
                  </div>
                  <div>
                    <div className="text-[9px] text-cyan-400">CURRENT</div>
                    <div className="font-bold text-cyan-300">{markVerified ? `₹${trade.current_price.toLocaleString('en-IN')}` : '—'}</div>
                  </div>
                  <div>
                    <div className="text-[9px] text-rose-400">SL</div>
                    <div className="font-bold text-rose-300">₹{trade.stop_loss}</div>
                  </div>
                  <div>
                    <div className="text-[9px] text-emerald-400">TARGET</div>
                    <div className="font-bold text-emerald-300">₹{trade.target}</div>
                  </div>
                </div>

                {/* Square Off Button */}
                <div className="pt-1 flex justify-end">
                  <button
                    onClick={() => closePaperTrade(trade.id)}
                    disabled={!markVerified}
                    className="py-1 px-3 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 font-bold text-xs font-mono border border-rose-500/40 active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {markVerified ? 'SQUARE OFF POSITION' : 'WAIT FOR VERIFIED LTP'}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Closed Positions History */}
      {closedTrades.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-black text-slate-400 uppercase tracking-wider font-mono px-1">
            Closed Positions History ({closedTrades.length})
          </div>

          {closedTrades.map(trade => (
            <div
              key={trade.id}
              className="card-base p-3 border border-[#1C2740] bg-[#0E1524] flex items-center justify-between text-xs font-mono opacity-80"
            >
              <div>
                <div className="font-bold text-slate-200">{trade.option_name}</div>
                <div className="text-[10px] text-slate-500">
                  Exit at ₹{trade.exit_price} • Closed {trade.closed_at}
                </div>
              </div>
              <div className="text-right">
                {trade.mark_status === 'LIVE_OPTION_QUOTE' ? (
                  <>
                    <span className={`font-bold ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {trade.pnl >= 0 ? '+' : ''}₹{trade.pnl.toLocaleString('en-IN')}
                    </span>
                    <div className="text-[9px] text-slate-500">{trade.pnl_percent >= 0 ? '+' : ''}{trade.pnl_percent.toFixed(2)}%</div>
                  </>
                ) : <span className="text-slate-500">P&amp;L not verified</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* New Order Modal Dialog */}
      {orderModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm" onClick={() => setOrderModalOpen(false)} />
          <div className="relative w-full max-w-sm card-base p-5 border border-[#1C2740] bg-[#121A2D] z-10 space-y-4">
            <div className="flex items-center justify-between border-b border-[#1C2740] pb-2">
              <span className="text-sm font-black text-white font-mono">PLACE PAPER ORDER</span>
              <button onClick={() => setOrderModalOpen(false)} className="text-slate-400 hover:text-white">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handlePlaceOrder} className="space-y-3 font-mono text-xs">
              <div>
                <label className="text-slate-400 block mb-1">Index Instrument</label>
                <select
                  value={orderSymbol}
                  onChange={e => setOrderSymbol(e.target.value as IndexSymbol)}
                  className="w-full p-2 rounded-xl bg-[#070B12] border border-[#1C2740] text-white"
                >
                  {(['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX'] as IndexSymbol[]).map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Option Type</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setOrderSide('CE')}
                    className={`py-2 rounded-xl font-bold ${
                      orderSide === 'CE' ? 'bg-emerald-500 text-[#070B12]' : 'bg-[#070B12] text-slate-300'
                    }`}
                  >
                    CALL (CE)
                  </button>
                  <button
                    type="button"
                    onClick={() => setOrderSide('PE')}
                    className={`py-2 rounded-xl font-bold ${
                      orderSide === 'PE' ? 'bg-rose-500 text-white' : 'bg-[#070B12] text-slate-300'
                    }`}
                  >
                    PUT (PE)
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-slate-400 block mb-1">Lots</label>
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={orderLots}
                    onChange={e => setOrderLots(parseInt(e.target.value) || 1)}
                    className="w-full p-2 rounded-xl bg-[#070B12] border border-[#1C2740] text-white"
                  />
                </div>
                <div>
                  <label className="text-slate-400 block mb-1">Price (₹)</label>
                  <input
                    type="number"
                    step="0.5"
                    value={orderPrice}
                    onChange={e => setOrderPrice(parseFloat(e.target.value) || 0)}
                    className="w-full p-2 rounded-xl bg-[#070B12] border border-[#1C2740] text-white"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-2.5 rounded-xl bg-cyan-500 text-[#070B12] font-black text-xs mt-2 shadow-lg shadow-cyan-500/20 active:scale-95 transition-all"
              >
                SUBMIT VIRTUAL ORDER
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
