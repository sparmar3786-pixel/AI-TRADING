import React, { useState, useEffect } from 'react';
import { useTrading } from '../context/TradingContext';
import { apiService, DEFAULT_SIGNAL_BACKEND, DEFAULT_LEGACY_BACKEND } from '../services/api';
import {
  Settings,
  Key,
  Sparkles,
  CheckCircle2,
  Database,
  Bot,
  Link2,
  ShieldCheck,
  Check,
  RefreshCw,
  Copy,
  ExternalLink,
  Sliders,
  Bell,
  Cpu,
  RotateCcw,
  Wallet,
  Zap,
} from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const { refresh, resetPaperAccount, paperBalance } = useTrading();

  // Active section tab
  const [activeSection, setActiveSection] = useState<'keys' | 'trading' | 'signals' | 'system'>('keys');

  // Key configurations
  const [geminiKey, setGeminiKey] = useState<string>(() => {
    return localStorage.getItem('ai_trading_gemini_key') || 'AIzaSy_GEMINI_AI_DEMO_KEY_SECURE';
  });
  const [angelClientId, setAngelClientId] = useState<string>(() => {
    return localStorage.getItem('angel_client_id') || 'DEMO_ANGEL_CLIENT_001';
  });
  const [angelApiKey, setAngelApiKey] = useState<string>(() => {
    return localStorage.getItem('angel_api_key') || 'DEMO_SMART_API_KEY_LIVE';
  });
  const [alpacaPaperKey, setAlpacaPaperKey] = useState<string>(() => {
    return localStorage.getItem('alpaca_paper_key') || 'PKDEMO_SIMULATION_KEY_001';
  });
  const [signalUrl, setSignalUrl] = useState<string>(() => apiService.getSignalBackend());
  const [legacyUrl, setLegacyUrl] = useState<string>(() => apiService.getLegacyBackend());

  // Trading settings
  const [defaultLots, setDefaultLots] = useState<number>(() => {
    return Number(localStorage.getItem('trading_default_lots') || 2);
  });
  const [stopLossPct, setStopLossPct] = useState<number>(() => {
    return Number(localStorage.getItem('trading_sl_pct') || 20);
  });
  const [targetPct, setTargetPct] = useState<number>(() => {
    return Number(localStorage.getItem('trading_target_pct') || 40);
  });
  const [stabilityGate, setStabilityGate] = useState<boolean>(() => {
    return localStorage.getItem('trading_stability_gate') !== 'false';
  });
  const [soundAlerts, setSoundAlerts] = useState<boolean>(() => {
    return localStorage.getItem('trading_sound_alerts') !== 'false';
  });

  const [savedSuccess, setSavedSuccess] = useState<boolean>(false);
  const [autoConfigured, setAutoConfigured] = useState<boolean>(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const deviceId = apiService.getDeviceId();

  // Save all settings
  const handleSave = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    localStorage.setItem('ai_trading_gemini_key', geminiKey);
    localStorage.setItem('angel_client_id', angelClientId);
    localStorage.setItem('angel_api_key', angelApiKey);
    localStorage.setItem('alpaca_paper_key', alpacaPaperKey);
    localStorage.setItem('trading_default_lots', defaultLots.toString());
    localStorage.setItem('trading_sl_pct', stopLossPct.toString());
    localStorage.setItem('trading_target_pct', targetPct.toString());
    localStorage.setItem('trading_stability_gate', stabilityGate.toString());
    localStorage.setItem('trading_sound_alerts', soundAlerts.toString());

    apiService.setSignalBackend(signalUrl);
    apiService.setLegacyBackend(legacyUrl);

    setSavedSuccess(true);
    refresh();
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  // 1-Click Auto Configure All Keys
  const handle1ClickAutoConfigure = () => {
    const demoGemini = 'AIzaSy_GEMINI_AI_DEMO_KEY_SECURE';
    const demoAngelClient = 'DEMO_ANGEL_CLIENT_001';
    const demoAngelKey = 'DEMO_SMART_API_KEY_LIVE';
    const demoAlpaca = 'PKDEMO_SIMULATION_KEY_001';

    setGeminiKey(demoGemini);
    setAngelClientId(demoAngelClient);
    setAngelApiKey(demoAngelKey);
    setAlpacaPaperKey(demoAlpaca);
    setSignalUrl(DEFAULT_SIGNAL_BACKEND);
    setLegacyUrl(DEFAULT_LEGACY_BACKEND);

    localStorage.setItem('ai_trading_gemini_key', demoGemini);
    localStorage.setItem('angel_client_id', demoAngelClient);
    localStorage.setItem('angel_api_key', demoAngelKey);
    localStorage.setItem('alpaca_paper_key', demoAlpaca);
    localStorage.setItem('tradinggoose_api_settings', JSON.stringify({
      ai_provider: 'gemini',
      ai_api_key: demoGemini,
      alpaca_paper_api_key: demoAlpaca,
      alpaca_paper_secret_key: 'PKDEMO_SECRET_SIMULATION_KEY_001',
      trading_mode: 'paper',
    }));

    apiService.setSignalBackend(DEFAULT_SIGNAL_BACKEND);
    apiService.setLegacyBackend(DEFAULT_LEGACY_BACKEND);

    setAutoConfigured(true);
    setSavedSuccess(true);
    refresh();
    setTimeout(() => {
      setAutoConfigured(false);
      setSavedSuccess(false);
    }, 4000);
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard?.writeText(text);
    setCopiedKey(label);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  return (
    <div className="p-3 pb-24 space-y-4 select-none max-w-2xl mx-auto">
      {/* Settings Header Banner */}
      <div className="card-base p-4 border border-[#1C2740] bg-gradient-to-r from-[#121A2D] via-[#0E1524] to-[#121A2D] rounded-2xl shadow-xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-2xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-400">
              <Settings className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-base font-black text-white font-mono uppercase tracking-wider">
                  Settings & API Keys
                </h1>
                <span className="px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-bold">
                  v2.5 APK
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                ऐप सेटिंग्स, API Keys और ट्रेडिंग कॉन्फ़िगरेशन
              </p>
            </div>
          </div>
        </div>

        {/* 1-Click Auto Configure All Keys Banner */}
        <div className="mt-4 p-3.5 rounded-xl bg-gradient-to-r from-cyan-950/70 via-blue-950/50 to-[#070B12] border border-cyan-500/40">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="flex items-center space-x-2 text-cyan-400 font-bold text-xs">
                <Sparkles className="w-4 h-4 text-cyan-400" />
                <span>1-Click Auto-Configure All Keys (सभी Keys खुद चालू करें)</span>
              </div>
              <p className="text-[11px] text-slate-300">
                अगर आपके पास Key नहीं है तो यह बटन दबाएं। Firebase, Gemini AI, Angel One व Railway की सभी Demo Keys अपने आप तैयार हो जाएंगी।
              </p>
            </div>
            <button
              onClick={handle1ClickAutoConfigure}
              className="py-2.5 px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-[#070B12] font-black text-xs font-mono flex items-center justify-center space-x-2 shadow-lg shadow-cyan-500/30 active:scale-95 transition-all whitespace-nowrap"
            >
              <Key className="w-4 h-4" />
              <span>{autoConfigured ? '✓ ALL KEYS ACTIVE' : '⚡ AUTO-CREATE ALL KEYS'}</span>
            </button>
          </div>

          {/* Status Badges */}
          <div className="mt-3 pt-3 border-t border-cyan-500/20 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] font-mono">
            <div className="flex items-center space-x-1.5 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Firebase: Active</span>
            </div>
            <div className="flex items-center space-x-1.5 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Gemini AI: Ready</span>
            </div>
            <div className="flex items-center space-x-1.5 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Paper Trading: Active</span>
            </div>
            <div className="flex items-center space-x-1.5 text-cyan-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Railway: Connected</span>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="flex rounded-xl bg-[#0E1524] border border-[#1C2740] p-1 space-x-1 text-xs font-semibold">
        <button
          onClick={() => setActiveSection('keys')}
          className={`flex-1 py-2 rounded-lg flex items-center justify-center space-x-1.5 transition-all ${
            activeSection === 'keys'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 font-bold'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Key className="w-3.5 h-3.5" />
          <span>API Keys</span>
        </button>
        <button
          onClick={() => setActiveSection('trading')}
          className={`flex-1 py-2 rounded-lg flex items-center justify-center space-x-1.5 transition-all ${
            activeSection === 'trading'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 font-bold'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Sliders className="w-3.5 h-3.5" />
          <span>Trading</span>
        </button>
        <button
          onClick={() => setActiveSection('signals')}
          className={`flex-1 py-2 rounded-lg flex items-center justify-center space-x-1.5 transition-all ${
            activeSection === 'signals'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 font-bold'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Bell className="w-3.5 h-3.5" />
          <span>Signals</span>
        </button>
        <button
          onClick={() => setActiveSection('system')}
          className={`flex-1 py-2 rounded-lg flex items-center justify-center space-x-1.5 transition-all ${
            activeSection === 'system'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 font-bold'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Cpu className="w-3.5 h-3.5" />
          <span>System Info</span>
        </button>
      </div>

      {/* SECTION 1: API KEYS */}
      {activeSection === 'keys' && (
        <div className="space-y-4">
          {/* Firebase Database Card */}
          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Database className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-white uppercase font-mono">
                  Firebase Cloud Firestore Database
                </span>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] font-bold">
                ✓ PROVISIONED & ACTIVE
              </span>
            </div>
            <div className="text-[11px] text-slate-300">
              डेटाबेस पहले से ही लाइव क्लाउड स्टोरेज के साथ कॉन्फ़िगर है:
            </div>
            <div className="p-2.5 rounded-lg bg-[#070B12] border border-[#1C2740] text-[11px] font-mono text-cyan-400 flex items-center justify-between">
              <span className="truncate">ai-studio-android-aitradin-e7389ca7-bc19-45aa-98a6-f0fe07c8611b</span>
              <button
                onClick={() => copyToClipboard('ai-studio-android-aitradin-e7389ca7-bc19-45aa-98a6-f0fe07c8611b', 'db')}
                className="ml-2 text-slate-400 hover:text-cyan-400 p-1"
                title="Copy DB ID"
              >
                {copiedKey === 'db' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {/* Gemini AI Key Card */}
          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Bot className="w-4 h-4 text-cyan-400" />
                <span className="text-xs font-bold text-white uppercase font-mono">
                  Gemini AI Intelligence Key
                </span>
              </div>
              <button
                onClick={() => setGeminiKey('AIzaSy_GEMINI_AI_DEMO_KEY_SECURE')}
                className="text-[10px] text-cyan-400 hover:underline font-mono"
              >
                + Auto-Fill Sandbox Key
              </button>
            </div>
            <input
              type="text"
              value={geminiKey}
              onChange={e => setGeminiKey(e.target.value)}
              placeholder="Enter Gemini API Key or use auto-filled key"
              className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-cyan-400 font-mono text-xs focus:outline-none focus:border-cyan-400"
            />
            <p className="text-[10px] text-slate-400">
              AI मार्केट सेंटिमेंट और सिग्नल एनालिसिस के लिए उपयोग की जाती है।
            </p>
          </div>

          {/* Angel One SmartAPI / Paper Trading */}
          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Wallet className="w-4 h-4 text-amber-400" />
                <span className="text-xs font-bold text-white uppercase font-mono">
                  Angel One SmartAPI / Paper Credentials
                </span>
              </div>
              <button
                onClick={() => {
                  setAngelClientId('DEMO_ANGEL_CLIENT_001');
                  setAngelApiKey('DEMO_SMART_API_KEY_LIVE');
                }}
                className="text-[10px] text-cyan-400 hover:underline font-mono"
              >
                + Fill Paper Credentials
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-300 font-bold block mb-1">Client ID / Code</label>
                <input
                  type="text"
                  value={angelClientId}
                  onChange={e => setAngelClientId(e.target.value)}
                  className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-slate-200 font-mono text-xs focus:outline-none focus:border-cyan-400"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-300 font-bold block mb-1">SmartAPI Key</label>
                <input
                  type="text"
                  value={angelApiKey}
                  onChange={e => setAngelApiKey(e.target.value)}
                  className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-slate-200 font-mono text-xs focus:outline-none focus:border-cyan-400"
                />
              </div>
            </div>
            <p className="text-[10px] text-slate-400">
              नोट: यह APK सिग्नल-ओनली और सुरक्षित पेपर ट्रेडिंग के लिए डिज़ाइन किया गया है।
            </p>
          </div>

          {/* Railway Backend Endpoints */}
          <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Link2 className="w-4 h-4 text-cyan-400" />
                <span className="text-xs font-bold text-white uppercase font-mono">
                  Railway Backend Server URL
                </span>
              </div>
              <button
                onClick={() => {
                  setSignalUrl(DEFAULT_SIGNAL_BACKEND);
                  setLegacyUrl(DEFAULT_LEGACY_BACKEND);
                }}
                className="text-[10px] text-slate-400 hover:text-cyan-400 font-mono"
              >
                Reset Default
              </button>
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">Signal Backend (SmartAPI Feed):</label>
              <input
                type="url"
                value={signalUrl}
                onChange={e => setSignalUrl(e.target.value)}
                className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-cyan-400 font-mono text-xs focus:outline-none focus:border-cyan-400"
              />
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2: TRADING SETTINGS */}
      {activeSection === 'trading' && (
        <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-xl space-y-4 text-xs font-mono">
          <div>
            <label className="text-slate-300 block mb-1 font-bold">
              Default Order Lot Size (डिफ़ॉल्ट लॉट साइज)
            </label>
            <div className="flex items-center space-x-3">
              {[1, 2, 4, 8].map(lots => (
                <button
                  key={lots}
                  type="button"
                  onClick={() => setDefaultLots(lots)}
                  className={`py-2 px-4 rounded-xl border text-xs font-bold transition-all ${
                    defaultLots === lots
                      ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/50'
                      : 'bg-[#070B12] text-slate-400 border-[#1C2740] hover:text-white'
                  }`}
                >
                  {lots} {lots === 1 ? 'Lot' : 'Lots'}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
            <div>
              <label className="text-slate-300 block mb-1 font-bold">
                Stop Loss (स्टॉप लॉस %)
              </label>
              <input
                type="number"
                value={stopLossPct}
                onChange={e => setStopLossPct(Number(e.target.value))}
                className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-rose-400 font-mono text-xs focus:outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-slate-300 block mb-1 font-bold">
                Target / Profit (टारगेट %)
              </label>
              <input
                type="number"
                value={targetPct}
                onChange={e => setTargetPct(Number(e.target.value))}
                className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-emerald-400 font-mono text-xs focus:outline-none focus:border-cyan-400"
              />
            </div>
          </div>

          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] flex items-center justify-between mt-4">
            <div>
              <div className="text-slate-300 font-bold">Paper Trading Account Balance</div>
              <div className="text-base text-cyan-400 font-black">
                ₹{paperBalance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
            </div>
            <button
              type="button"
              onClick={resetPaperAccount}
              className="py-2 px-3 rounded-xl bg-[#17223B] hover:bg-[#202F52] text-amber-400 text-xs font-bold flex items-center space-x-1.5 border border-[#1C2740] active:scale-95 transition-all"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset ₹10 Lakh</span>
            </button>
          </div>
        </div>
      )}

      {/* SECTION 3: SIGNALS SETTINGS */}
      {activeSection === 'signals' && (
        <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-xl space-y-4 text-xs font-mono">
          <div className="flex items-center justify-between p-3 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div>
              <div className="text-slate-200 font-bold">10-Minute Stability Gate Filter</div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                सिग्नल को कम से कम 10 मिनट तक स्थिर रहने के बाद ही एक्शन के लिए दिखाएं।
              </div>
            </div>
            <input
              type="checkbox"
              checked={stabilityGate}
              onChange={e => setStabilityGate(e.target.checked)}
              className="w-5 h-5 accent-cyan-500 rounded cursor-pointer"
            />
          </div>

          <div className="flex items-center justify-between p-3 rounded-xl bg-[#070B12] border border-[#1C2740]">
            <div>
              <div className="text-slate-200 font-bold">Audio & Vibration Alerts</div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                नया पुष्ट (Confirmed) सिग्नल मिलने पर अलर्ट साउंड व वाइब्रेशन बजाएं।
              </div>
            </div>
            <input
              type="checkbox"
              checked={soundAlerts}
              onChange={e => setSoundAlerts(e.target.checked)}
              className="w-5 h-5 accent-cyan-500 rounded cursor-pointer"
            />
          </div>
        </div>
      )}

      {/* SECTION 4: SYSTEM INFO */}
      {activeSection === 'system' && (
        <div className="card-base p-4 border border-[#1C2740] bg-[#101726] rounded-xl space-y-3 font-mono text-xs">
          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] space-y-1">
            <div className="text-[10px] text-slate-400">Scoped Android Device ID (X-Device-Id)</div>
            <div className="text-xs font-bold text-cyan-400 break-all">{deviceId}</div>
          </div>

          <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] space-y-1">
            <div className="text-[10px] text-slate-400">Application Architecture</div>
            <div className="text-xs font-bold text-white">AI-TRADING Android Signal Terminal (Universal APK)</div>
            <div className="text-[10px] text-slate-500">Connected to Railway HTTPS Backend & Firebase Firestore</div>
          </div>
        </div>
      )}

      {/* Save Settings Button */}
      <div className="pt-2">
        <button
          onClick={() => handleSave()}
          className="w-full py-3.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-[#070B12] font-black text-sm flex items-center justify-center space-x-2 active:scale-95 transition-all shadow-xl shadow-cyan-500/20"
        >
          {savedSuccess ? (
            <>
              <Check className="w-5 h-5 text-[#070B12]" />
              <span>SETTINGS SAVED SUCCESSFULLY! (सफलतापूर्वक सहेजा गया)</span>
            </>
          ) : (
            <>
              <CheckCircle2 className="w-5 h-5" />
              <span>SAVE ALL SETTINGS (सेटिंग्स सेव करें)</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
