import React, { useCallback, useEffect, useState } from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService } from '../services/api';
import { sanitizeRepositoryLinks } from '../services/repositoryLinkFilter';
import {
  nvidiaService,
  SUPPORTED_NVIDIA_MODELS,
  MarketArticle,
} from '../services/nvidiaService';
import {
  BrainCircuit,
  RefreshCw,
  AlertTriangle,
  ExternalLink,
  Newspaper,
  Sparkles,
  Key,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Sliders,
  TrendingUp,
  Shield,
  Layers,
} from 'lucide-react';



export const MarketIntelligencePage: React.FC = () => {
  const { selectedIndex, market, signals } = useTrading();

  // NVIDIA Config State
  const [showConfig, setShowConfig] = useState(false);
  const [nvidiaKey, setNvidiaKey] = useState(() => nvidiaService.getNvidiaApiKey());
  const [selectedModel, setSelectedModel] = useState(() => nvidiaService.getSelectedModel());
  const [keyTesting, setKeyTesting] = useState(false);
  const [keyStatusMessage, setKeyStatusMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [nvidiaBackendStatus, setNvidiaBackendStatus] = useState<{ configured: boolean; active: boolean }>({ configured: false, active: false });

  // Intelligence State
  const [summary, setSummary] = useState<string>('');
  const [summaryProvider, setSummaryProvider] = useState<string>('');
  const [summaryModel, setSummaryModel] = useState<string>('');
  const [articles, setArticles] = useState<MarketArticle[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string>('');
  const [nextRefreshAt, setNextRefreshAt] = useState<string>('');
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentMarket = market[selectedIndex];
  const currentSignal = signals[selectedIndex];

  // Generate or load market intelligence brief
  const loadIntelligence = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);

    try {
      // 1. Try querying backend for live data
      const backendUrl = apiService.getSignalBackend().replace(/\/+$/, '');
      let backendLoaded = false;
      let backendFailure = '';

      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);

        let response: Response;
        try {
          response = await fetch(`${backendUrl}/v1/market-intelligence`, {
            headers: await apiService.getAuthHeaders(),
            signal: controller.signal,
            cache: 'no-store',
          });
        } finally {
          clearTimeout(timeoutId);
        }

        if (!response.ok) {
          throw new Error(`Market intelligence API returned HTTP ${response.status}.`);
        }
        const body = sanitizeRepositoryLinks(await response.json()) as any;
        if (body && typeof body.summary === 'string' && body.summary.trim() &&
            body.summary_provider && body.summary_model && body.updated_at) {
          setSummary(body.summary);
          setSummaryProvider(String(body.summary_provider));
          setSummaryModel(String(body.summary_model));
          setUpdatedAt(String(body.updated_at));
          setNextRefreshAt(body.next_refresh_at || '');
          setArticles(Array.isArray(body.articles) ? body.articles : []);
          backendLoaded = true;
        } else {
          throw new Error('Backend has no verified market-intelligence result yet; refresh after the cloud inference finishes.');
        }
      } catch (backendError) {
        // Keep the real HTTP/network failure visible instead of masking it as a generic AI status.
        backendFailure = backendError instanceof Error ? backendError.message : String(backendError);
      }

      // Never replace a failed cloud request with synthetic prices, fabricated news,
      // or a template falsely labelled NVIDIA inference.
      if (!backendLoaded) {
        setSummary('');
        setSummaryProvider('');
        setSummaryModel('');
        setUpdatedAt('');
        setNextRefreshAt('');
        setArticles([]);
        throw new Error(`Cloud market intelligence unavailable: ${backendFailure || 'backend returned an empty or unverified response'}. Check the configured Railway URL, endpoint deployment, CORS, and server-side NVIDIA/Exa/Tavily configuration.`);
      }

      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error generating market intelligence');
    } finally {
      setRefreshing(false);
    }
  }, [selectedIndex]);

  // Initial load and periodic refresh
  useEffect(() => {
    void nvidiaService.refreshNvidiaStatus().then(setNvidiaBackendStatus);
    void loadIntelligence();
    const interval = setInterval(() => {
      void loadIntelligence();
    }, 15 * 60 * 1000);
    return () => clearInterval(interval);
  }, [loadIntelligence]);

  // Handle NVIDIA Key Save and Validation
  const handleTestAndSaveKey = async () => {
    if (!nvidiaKey.trim()) {
      nvidiaService.setNvidiaApiKey('');
      setKeyStatusMessage({ text: 'Direct NVIDIA key removed. Cloud AI status will depend on a verified server response.', ok: true });
      void loadIntelligence(true);
      return;
    }

    setKeyTesting(true);
    setKeyStatusMessage(null);

    const result = await nvidiaService.validateNvidiaKey(nvidiaKey);
    setKeyTesting(false);

    if (result.valid) {
      nvidiaService.setNvidiaApiKey(nvidiaKey);
      nvidiaService.setSelectedModel(selectedModel);
      setKeyStatusMessage({ text: 'NVIDIA key authenticated at the models endpoint. Actual chat inference is verified only after a successful AI response.', ok: true });
      void loadIntelligence(true);
      setTimeout(() => setShowConfig(false), 2000);
    } else {
      setKeyStatusMessage({ text: `❌ ${result.message}`, ok: false });
    }
  };

  const isDirectKey = nvidiaBackendStatus.configured;

  return (
    <div className="p-3 pb-24 space-y-4 select-none max-w-3xl mx-auto">
      {/* AI Market Intelligence Banner */}
      <div className="card-base p-4 border border-[#1C2740] bg-gradient-to-r from-[#121A2D] via-[#0D1527] to-[#121A2D] rounded-2xl shadow-xl space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-2xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-400">
              <BrainCircuit className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-sm font-black text-white font-mono uppercase tracking-wider">
                  NVIDIA AI Market Intelligence
                </h2>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold font-mono border flex items-center gap-1 ${
                  summaryProvider && updatedAt && !error
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${summaryProvider && updatedAt && !error ? 'bg-emerald-400' : 'bg-rose-400'}`}></span>
                  {summaryProvider && updatedAt && !error ? `INFERENCE RESULT: ${summaryProvider}` : isDirectKey ? 'NVIDIA KEY CONFIGURED • NOT VERIFIED' : 'CLOUD AI NOT VERIFIED'}
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                {selectedIndex} Confluence • NVIDIA Cloud AI • 5-Layer Quant Context
              </p>
            </div>
          </div>

          <button
            onClick={() => setShowConfig(!showConfig)}
            className="px-3 py-1.5 rounded-xl bg-[#17223B] border border-[#2A3B5C] hover:border-cyan-400 text-xs font-semibold text-slate-200 flex items-center gap-1.5 transition-colors"
          >
            <Sliders className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">NVIDIA Key</span>
            {showConfig ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Expandable NVIDIA Key Configuration Panel */}
        {showConfig && (
          <div className="p-4 rounded-xl bg-[#090E17] border border-[#1C2740] space-y-3 mt-3 animate-fadeIn">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2 text-xs font-bold text-white font-mono">
                <Key className="w-4 h-4 text-cyan-400" />
                <span>NVIDIA NIM API KEY CONFIGURATION</span>
              </div>
              <a
                href="https://build.nvidia.com"
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-cyan-400 hover:underline flex items-center gap-1 font-mono"
              >
                Get Free Key (build.nvidia.com) <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <p className="text-[11px] text-slate-300 leading-relaxed">
              NVIDIA key is stored in this browser for direct requests. The key check verifies model-catalog access only; the UI reports AI as connected only after a real response. Without a direct key, server-side NVIDIA/OpenRouter inference is attempted; no synthetic AI answer is substituted.
            </p>

            <div className="space-y-2">
              <input
                type="password"
                value={nvidiaKey}
                onChange={e => setNvidiaKey(e.target.value)}
                placeholder="nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                className="w-full p-2.5 rounded-xl bg-[#101726] border border-[#1C2740] text-white text-xs font-mono focus:outline-none focus:border-cyan-400"
              />

              <div className="flex flex-col sm:flex-row gap-2">
                <select
                  value={selectedModel}
                  onChange={e => setSelectedModel(e.target.value)}
                  className="flex-1 p-2 rounded-xl bg-[#101726] border border-[#1C2740] text-white text-xs font-mono focus:outline-none focus:border-cyan-400"
                >
                  {SUPPORTED_NVIDIA_MODELS.map(m => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  onClick={handleTestAndSaveKey}
                  disabled={keyTesting}
                  className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#070B12] font-black text-xs font-mono flex items-center justify-center gap-1.5 disabled:opacity-50"
                >
                  {keyTesting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                  {keyTesting ? 'TESTING...' : 'TEST & SAVE KEY'}
                </button>
              </div>

              {keyStatusMessage && (
                <div className={`p-2.5 rounded-xl text-xs font-mono ${
                  keyStatusMessage.ok ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30' : 'bg-rose-500/10 text-rose-300 border border-rose-500/30'
                }`}>
                  {keyStatusMessage.text}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="card-base p-3 border border-amber-500/40 bg-amber-500/5 flex items-start gap-2 text-xs text-amber-200">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
          <span>Notice: {error} (Built-in Quant Engine remains fully active).</span>
        </div>
      )}

      {/* Scheduled Market Brief Card */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-2xl space-y-3 shadow-lg">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <div className="text-xs font-bold text-white font-mono uppercase">
              {selectedIndex} SCHEDULED MARKET BRIEF
            </div>
          </div>

          <button
            onClick={() => void loadIntelligence(true)}
            disabled={refreshing}
            className="px-3 py-1.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#070B12] disabled:opacity-50 text-[10px] font-black flex items-center gap-1.5 transition-all shadow-md shadow-cyan-500/20"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'REFRESHING...' : 'REFRESH INTEL'}
          </button>
        </div>

        {/* Real-time Status Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] font-mono">
          <div className="p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-slate-500">AI ENGINE</div>
            <div className="text-cyan-400 font-bold mt-1 truncate">{summaryProvider || 'NOT VERIFIED'}</div>
          </div>
          <div className="p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-slate-500">ACTIVE MODEL</div>
            <div className="text-white font-bold mt-1 truncate">{summaryModel || 'NOT VERIFIED'}</div>
          </div>
          <div className="p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-slate-500">LAST INFERENCE</div>
            <div className="text-white font-bold mt-1">{updatedAt ? new Date(updatedAt).toLocaleTimeString('en-IN') : 'No inference yet'}</div>
          </div>
          <div className="p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div className="text-slate-500">{selectedIndex} SPOT</div>
            <div className="text-emerald-300 font-bold mt-1">{typeof currentMarket?.ltp === 'number' ? `₹${currentMarket.ltp.toLocaleString('en-IN')}` : 'Unavailable'}</div>
          </div>
        </div>

        {/* Brief Text */}
        <div className="p-3.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-xs text-slate-200 leading-relaxed whitespace-pre-wrap font-sans">
          {summary || error || 'Waiting for a verified cloud inference result...'}
        </div>
      </div>

      {/* Source-Backed News Evidence */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-2xl space-y-3 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold text-white font-mono">
            <Newspaper className="w-4 h-4 text-cyan-400" />
            <span>REAL-TIME MARKET CATALYSTS & NEWS ({articles.length})</span>
          </div>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold font-mono ${articles.length ? 'bg-emerald-500/10 text-emerald-300' : 'bg-rose-500/10 text-rose-300'}`}>
            {articles.length ? 'BACKEND EVIDENCE' : 'NO VERIFIED EVIDENCE'}
          </span>
        </div>

        <div className="space-y-2.5">
          {articles.map((article, idx) => (
            <div
              key={idx}
              className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] space-y-1.5 hover:border-cyan-500/30 transition-all"
            >
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span className="text-cyan-300 font-bold">{article.source} • {article.index}</span>
                <span className={`px-2 py-0.5 rounded-md font-bold ${
                  article.sentiment === 'BULLISH'
                    ? 'bg-emerald-500/20 text-emerald-300'
                    : article.sentiment === 'BEARISH'
                    ? 'bg-rose-500/20 text-rose-300'
                    : 'bg-amber-500/20 text-amber-300'
                }`}>
                  {article.sentiment}
                </span>
              </div>
              <div className="text-xs text-slate-100 font-semibold">{article.title}</div>
              <p className="text-[11px] text-slate-300 leading-relaxed">{article.content}</p>
              {article.url && (
                <a
                  href={article.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[10px] text-cyan-400 hover:underline pt-0.5"
                >
                  Read Source Article <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          ))}
        </div>
      </div>


    </div>
  );
};
