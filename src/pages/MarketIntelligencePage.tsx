import React, { useCallback, useEffect, useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService } from '../services/api';
import { generateMarketIntelligenceAnswer } from '../services/aiIntelligence';
import { BrainCircuit, Send, RefreshCw, AlertTriangle, ExternalLink, Newspaper, Sparkles } from 'lucide-react';

type Article = {
  index?: string;
  title?: string;
  url?: string;
  published_at?: string | null;
  source?: string;
  content?: string;
};
type MarketContext = {
  ltp?: number | null;
  live?: boolean;
  source_timestamp?: string | null;
  age_seconds?: number | null;
  data_status?: string;
};
type ProviderCheck = {
  configured?: boolean;
  ok?: boolean;
  result_count?: number;
  last_error_status?: string;
};
type IntelligenceState = {
  status?: string;
  summary?: string | null;
  articles?: Article[];
  market_context?: Record<string, MarketContext>;
  provider_checks?: Record<string, ProviderCheck>;
  updated_at?: string | null;
  next_refresh_at?: string | null;
  refresh_interval_seconds?: number;
  summary_provider?: string | null;
  summary_model?: string | null;
  error?: string | null;
  refreshing?: boolean;
};
type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  provider?: string;
  model?: string;
};

const formatTime = (value?: string | null) => {
  if (!value) return 'Not available';
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : value;
};

const backendBase = () => apiService.getSignalBackend().replace(/\/+$/, '');
const deviceHeaders = () => ({
  Accept: 'application/json',
  'X-Device-Id': apiService.getDeviceId(),
});

export const MarketIntelligencePage: React.FC = () => {
  const { selectedIndex, market, signals } = useTrading();
  const [intel, setIntel] = useState<IntelligenceState>({});
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const loadIntelligence = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${backendBase()}/v1/market-intelligence`, {
        headers: deviceHeaders(),
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      setIntel(body as IntelligenceState);
      setError(null);
      setRefreshing(Boolean(body?.refreshing));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Market intelligence request failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadIntelligence();
    // Poll the cached server result; the backend performs the actual 15-minute refresh.
    const pollId = window.setInterval(() => { void loadIntelligence(); }, 30000);
    return () => window.clearInterval(pollId);
  }, [loadIntelligence]);

  const refreshNews = async () => {
    setRefreshing(true);
    try {
      const response = await fetch(`${backendBase()}/v1/market-intelligence/refresh`, {
        method: 'POST',
        headers: deviceHeaders(),
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      setIntel(body as IntelligenceState);
      setError(null);
      window.setTimeout(() => { void loadIntelligence(); }, 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'News refresh request failed');
      setRefreshing(false);
    }
  };

  const askNvidia = async (e: React.FormEvent) => {
    e.preventDefault();
    const prompt = question.trim();
    if (!prompt || chatBusy) return;
    const previous = messages;
    setMessages(prev => [...prev, { role: 'user', content: prompt }]);
    setQuestion('');
    setChatBusy(true);
    try {
      let answered = false;
      try {
        const response = await fetch(`${backendBase()}/v1/ai/nvidia-chat`, {
          method: 'POST',
          headers: { ...deviceHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            index: selectedIndex,
            question: prompt,
            history: previous.map(({ role, content }) => ({ role, content })),
          }),
        });
        if (response.ok) {
          const body = await response.json();
          const answer = typeof body?.answer === 'string' ? body.answer : '';
          if (answer.trim()) {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: answer,
              provider: String(body.provider || 'NVIDIA NIM'),
              model: typeof body.model === 'string' ? body.model : undefined,
            }]);
            answered = true;
          }
        }
      } catch (_) {
        // Fallback to built-in free AI intelligence
      }

      if (!answered) {
        const fallbackAi = await generateMarketIntelligenceAnswer({
          index: selectedIndex,
          question: prompt,
          market: market[selectedIndex],
          signal: signals[selectedIndex],
        });
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: fallbackAi.answer,
          provider: fallbackAi.provider,
          model: fallbackAi.model,
        }]);
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : 'AI request processing error';
      setError(message);
    } finally {
      setChatBusy(false);
    }
  };

  const context = intel.market_context?.[selectedIndex];
  const age = context?.age_seconds;
  const contextFresh = context?.live === true && typeof age === 'number' && age >= 0 && age <= 120;
  const articles = Array.isArray(intel.articles) ? intel.articles : [];
  const checks = intel.provider_checks || {};
  const intervalMinutes = Math.max(1, Math.round((intel.refresh_interval_seconds || 900) / 60));

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-3xl mx-auto">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400"><BrainCircuit className="w-5 h-5" /></div>
          <div>
            <h2 className="text-sm font-black text-white font-mono uppercase">AI Market Intelligence</h2>
            <p className="text-xs text-slate-400 font-mono">Exa + Tavily evidence • NVIDIA summary • every {intervalMinutes} min</p>
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold font-mono ${intel.summary_provider === 'nvidia' ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' : 'bg-amber-500/10 text-amber-300 border-amber-500/30'}`}>
          {intel.summary_provider === 'nvidia' ? 'NVIDIA INFERENCE OK' : 'NVIDIA NOT VERIFIED'}
        </span>
      </div>

      {error && (
        <div className="card-base p-3 border border-rose-500/40 bg-rose-500/5 flex items-start gap-2 text-xs text-rose-200">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>Backend request failed: {error}</span>
        </div>
      )}

      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs font-bold text-white font-mono">SCHEDULED MARKET BRIEF</div>
          <button onClick={refreshNews} disabled={refreshing || loading} className="px-3 py-2 rounded-lg bg-cyan-500 text-[#070B12] disabled:opacity-50 text-[10px] font-black flex items-center gap-1.5">
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'REFRESHING' : 'REFRESH NEWS'}
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] font-mono">
          <div className="p-2 rounded-lg bg-[#070B12]"><div className="text-slate-500">STATUS</div><div className="text-white font-bold mt-1">{intel.status || (loading ? 'LOADING' : 'UNKNOWN')}</div></div>
          <div className="p-2 rounded-lg bg-[#070B12]"><div className="text-slate-500">UPDATED</div><div className="text-white font-bold mt-1">{formatTime(intel.updated_at)}</div></div>
          <div className="p-2 rounded-lg bg-[#070B12]"><div className="text-slate-500">NEXT REFRESH</div><div className="text-white font-bold mt-1">{formatTime(intel.next_refresh_at)}</div></div>
          <div className="p-2 rounded-lg bg-[#070B12]"><div className="text-slate-500">{selectedIndex} DATA</div><div className={contextFresh ? 'text-emerald-300 font-bold mt-1' : 'text-rose-300 font-bold mt-1'}>{contextFresh ? `LIVE • ${context?.ltp ?? '—'}` : 'STALE / UNAVAILABLE'}</div></div>
        </div>
        {intel.summary ? (
          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] text-xs text-slate-200 leading-relaxed whitespace-pre-wrap">
            <div className="text-cyan-300 font-bold text-[10px] mb-2">{intel.summary_provider || 'UNKNOWN PROVIDER'}{intel.summary_model ? ` • ${intel.summary_model}` : ''}</div>
            {intel.summary}
          </div>
        ) : (
          <div className="p-3 rounded-xl bg-amber-500/5 border border-amber-500/30 text-xs text-amber-200">
            No verified NVIDIA summary is available yet. {intel.error || 'The backend must complete a real inference before a summary is shown.'}
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          {['exa', 'tavily'].map(name => {
            const check = checks[name];
            const ok = check?.configured === true && check?.ok === true;
            return (
              <div key={name} className="p-2 rounded-lg bg-[#070B12] border border-[#1C2740] flex items-center justify-between gap-2">
                <span className="text-[10px] font-bold text-white uppercase">{name}</span>
                <span className={`text-[10px] font-bold ${ok ? 'text-emerald-300' : 'text-rose-300'}`}>{ok ? `OK • ${check?.result_count ?? 0} results` : check?.configured ? 'ERROR / NO RESULTS' : 'NOT CONFIGURED'}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3">
        <div className="flex items-center gap-2 text-xs font-bold text-white"><Newspaper className="w-4 h-4 text-cyan-400" />SOURCE-BACKED NEWS ({articles.length})</div>
        {articles.length === 0 ? (
          <p className="text-xs text-slate-400">No news evidence returned. This is not interpreted as neutral sentiment.</p>
        ) : articles.map((article, index) => (
          <div key={article.url || `${article.title || 'article'}-${index}`} className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] space-y-1.5">
            <div className="text-[10px] text-cyan-300 font-bold">{article.index || 'MARKET'} • {article.source || 'Unknown source'} • {formatTime(article.published_at)}</div>
            <div className="text-xs text-slate-100 font-semibold">{article.title || 'Untitled evidence'}</div>
            {article.content && <p className="text-[11px] text-slate-400 leading-relaxed">{article.content}</p>}
            {article.url && <a href={article.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[10px] text-cyan-300 hover:underline">Open source <ExternalLink className="w-3 h-3" /></a>}
          </div>
        ))}
      </div>

      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-3">
        <div className="text-xs font-bold text-white font-mono">ASK NVIDIA ABOUT {selectedIndex}</div>
        <div className="space-y-3 max-h-72 overflow-y-auto">
          {messages.length === 0 && <p className="text-xs text-slate-400">Ask a question. Answers are shown only after the backend returns an actual inference response.</p>}
          {messages.map((message, index) => (
            <div key={index} className={`p-3 rounded-xl text-xs leading-relaxed whitespace-pre-wrap ${message.role === 'user' ? 'ml-6 bg-cyan-500/10 border border-cyan-500/30 text-white' : 'mr-2 bg-[#070B12] border border-[#1C2740] text-slate-200'}`}>
              {message.role === 'assistant' && <div className="text-[10px] text-cyan-300 font-bold mb-1">{message.provider || 'BACKEND'}{message.model ? ` • ${message.model}` : ''}</div>}
              {message.content}
            </div>
          ))}
        </div>
        <form onSubmit={askNvidia} className="flex items-center gap-2">
          <input value={question} onChange={e => setQuestion(e.target.value)} placeholder={`Ask about ${selectedIndex}...`} className="flex-1 min-w-0 p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-white text-xs font-mono focus:outline-none focus:border-cyan-400" />
          <button type="submit" disabled={!question.trim() || chatBusy} className="p-2.5 rounded-xl bg-cyan-500 text-[#070B12] disabled:opacity-50">
            {chatBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </form>
      </div>
    </div>
  );
};
