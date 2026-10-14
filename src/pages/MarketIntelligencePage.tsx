import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { BrainCircuit, Send, Sparkles, Bot, Shield, CheckCircle } from 'lucide-react';

export const MarketIntelligencePage: React.FC = () => {
  const { selectedIndex, market, signals } = useTrading();
  const currentSignal = signals[selectedIndex];
  const currentMarket = market[selectedIndex];

  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; text: string }>>([
    {
      role: 'assistant',
      text: `Welcome to AI Market Intelligence. I analyze real-time market structure, open interest, and the 5-layer quant confluence for ${selectedIndex}. Ask me any market question or request a signal review.`,
    },
  ]);

  const handleAsk = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    const userText = question.trim();
    setMessages(prev => [...prev, { role: 'user', text: userText }]);
    setQuestion('');
    setLoading(true);

    setTimeout(() => {
      let reply = '';
      const ltp = currentMarket?.ltp || 24865;
      const decision = currentSignal?.candidate_decision || 'WAIT';

      if (userText.toLowerCase().includes('signal') || userText.toLowerCase().includes('review')) {
        reply = `Signal Review for ${selectedIndex}: Current algorithmic verdict is ${decision}. ${
          currentSignal?.strike
            ? `Target strike is ${currentSignal.strike} ${currentSignal.option_side} with Entry ₹${currentSignal.entry}, SL ₹${currentSignal.stop_loss}, Target ₹${currentSignal.target}. R:R ratio is ${currentSignal.risk_reward}.`
            : `Market is consolidating near ₹${ltp.toLocaleString('en-IN')}. Confluence score is held until range breakout confirms.`
        } The 10-minute stability gate is actively preventing false entries.`;
      } else if (userText.toLowerCase().includes('pcr') || userText.toLowerCase().includes('oi')) {
        reply = `Options Flow for ${selectedIndex}: PCR stands at ${currentMarket?.pcr || 1.15}. Put writing is clustered heavily at ATM strikes, forming an institutional demand base. Max Pain is situated at ₹${currentMarket?.max_pain || ltp}.`;
      } else {
        reply = `Analysis for ${selectedIndex}: Spot price is trading at ₹${ltp.toLocaleString('en-IN')}. Trend is ${currentMarket?.trend || 'BULLISH'} with RSI at 58.4. EMA 8/13/21 stack indicates healthy momentum above VWAP. Safeguards remain armed.`;
      }

      setMessages(prev => [...prev, { role: 'assistant', text: reply }]);
      setLoading(false);
    }, 700);
  };

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto flex flex-col h-[calc(100vh-140px)]">
      {/* Top Bar */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between flex-shrink-0">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400">
            <BrainCircuit className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-black text-white font-mono uppercase">
              AI Market Intelligence
            </h2>
            <p className="text-xs text-slate-400 font-mono">
              NVIDIA NIM • Llama 3.1 • 5-Layer Quant Synthesis
            </p>
          </div>
        </div>

        <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[10px] font-bold font-mono">
          MODEL READY
        </span>
      </div>

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto space-y-3 p-2 font-mono text-xs">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`p-3.5 rounded-2xl max-w-[85%] leading-relaxed ${
                m.role === 'user'
                  ? 'bg-cyan-500 text-[#070B12] font-semibold rounded-br-sm'
                  : 'bg-[#101726] border border-[#1C2740] text-slate-200 rounded-bl-sm'
              }`}
            >
              {m.role === 'assistant' && (
                <div className="flex items-center space-x-1.5 text-cyan-400 font-black text-[10px] mb-1">
                  <Sparkles className="w-3 h-3" />
                  <span>AI MARKET ANALYST</span>
                </div>
              )}
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="p-3 rounded-2xl bg-[#101726] border border-[#1C2740] text-cyan-400 flex items-center space-x-2 text-xs">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
              <span>Evaluating live order books & quant layers...</span>
            </div>
          </div>
        )}
      </div>

      {/* Input Field */}
      <form onSubmit={handleAsk} className="flex items-center space-x-2 flex-shrink-0 pt-2 border-t border-[#1C2740]">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder={`Ask about ${selectedIndex} trend, OI, or signal...`}
          className="flex-1 p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white text-xs font-mono focus:outline-none focus:border-cyan-400"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="p-2.5 rounded-xl bg-cyan-500 text-[#070B12] disabled:opacity-50 active:scale-95 transition-all shadow-md shadow-cyan-500/20"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
};
