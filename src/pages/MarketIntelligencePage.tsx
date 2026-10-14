import React, { useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { BrainCircuit, Send, Sparkles, AlertTriangle } from 'lucide-react';

export const MarketIntelligencePage: React.FC = () => {
  const { selectedIndex, market, signals } = useTrading();
  const currentSignal = signals[selectedIndex];
  const currentMarket = market[selectedIndex];
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; text: string }>>([
    {
      role: 'assistant',
      text: 'AI inference is not connected to this frontend build. No market analysis will be simulated or presented as a real model response.',
    },
  ]);

  const handleAsk = (e: React.FormEvent) => {
    e.preventDefault();
    const userText = question.trim();
    if (!userText) return;
    setMessages(prev => [
      ...prev,
      { role: 'user', text: userText },
      {
        role: 'assistant',
        text: 'Request not sent: a verified NVIDIA chat endpoint and authenticated inference response are not available in the current frontend/backend branch. No AI analysis was run. Connect the real backend endpoint before relying on AI output.',
      },
    ]);
    setQuestion('');
  };

  const marketFresh = Boolean(currentMarket?.live && currentMarket?.timestamp && Date.now() - Date.parse(currentMarket.timestamp) <= 120000);
  const signalDecision = currentSignal?.decision || 'WAIT';

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto flex flex-col h-[calc(100vh-140px)]">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between flex-shrink-0">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400"><BrainCircuit className="w-5 h-5" /></div>
          <div>
            <h2 className="text-sm font-black text-white font-mono uppercase">AI Market Intelligence</h2>
            <p className="text-xs text-slate-400 font-mono">NVIDIA inference • status verified only after real response</p>
          </div>
        </div>
        <span className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30 text-[10px] font-bold font-mono">AI NOT VERIFIED</span>
      </div>

      <div className="card-base p-3 border border-[#1C2740] bg-[#101726] grid grid-cols-3 gap-2 text-[10px] font-mono">
        <div><div className="text-slate-500">SYMBOL</div><div className="text-white font-bold">{selectedIndex}</div></div>
        <div><div className="text-slate-500">DATA</div><div className={marketFresh ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>{marketFresh ? 'FRESH LIVE' : 'STALE / UNKNOWN'}</div></div>
        <div><div className="text-slate-500">SIGNAL</div><div className="text-white font-bold">{marketFresh ? signalDecision : 'WAIT'}</div></div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 p-2 font-mono text-xs">
        {messages.map((m, idx) => (
          <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`p-3.5 rounded-2xl max-w-[85%] leading-relaxed ${m.role === 'user' ? 'bg-cyan-500 text-[#070B12] font-semibold rounded-br-sm' : 'bg-[#101726] border border-[#1C2740] text-slate-200 rounded-bl-sm'}`}>
              {m.role === 'assistant' && <div className="flex items-center space-x-1.5 text-amber-300 font-black text-[10px] mb-1"><Sparkles className="w-3 h-3" /><span>BACKEND STATUS</span></div>}
              {m.text}
            </div>
          </div>
        ))}
      </div>

      <div className="card-base p-3 border border-amber-500/30 bg-amber-500/5 flex items-start gap-2 text-[11px] text-slate-300">
        <AlertTriangle className="w-4 h-4 text-amber-300 shrink-0" />
        <span>Chat is intentionally fail-closed. The current repository backend branch does not expose a verified chat route; this page will not fabricate an NVIDIA answer.</span>
      </div>

      <form onSubmit={handleAsk} className="flex items-center space-x-2 flex-shrink-0 pt-2 border-t border-[#1C2740]">
        <input type="text" value={question} onChange={e => setQuestion(e.target.value)} placeholder={`Ask about ${selectedIndex} (request won't reach AI until connected)`} className="flex-1 p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white text-xs font-mono focus:outline-none focus:border-cyan-400" />
        <button type="submit" disabled={!question.trim()} className="p-2.5 rounded-xl bg-cyan-500 text-[#070B12] disabled:opacity-50 active:scale-95 transition-all"><Send className="w-4 h-4" /></button>
      </form>
    </div>
  );
};
