import React, { useState } from 'react';
import { apiService, DEFAULT_SIGNAL_BACKEND, DEFAULT_LEGACY_BACKEND } from '../services/api';
import { useTrading } from '../context/TradingContext';
import { Settings, Shield, Link2, Check, RefreshCw } from 'lucide-react';

export const ApiSettingsPage: React.FC = () => {
  const { refresh } = useTrading();
  const [signalUrl, setSignalUrl] = useState(apiService.getSignalBackend());
  const [legacyUrl, setLegacyUrl] = useState(apiService.getLegacyBackend());
  const [saved, setSaved] = useState(false);
  const deviceId = apiService.getDeviceId();

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    apiService.setSignalBackend(signalUrl);
    apiService.setLegacyBackend(legacyUrl);
    setSaved(true);
    refresh();
    setTimeout(() => setSaved(false), 2500);
  };

  const handleReset = () => {
    setSignalUrl(DEFAULT_SIGNAL_BACKEND);
    setLegacyUrl(DEFAULT_LEGACY_BACKEND);
    apiService.setSignalBackend(DEFAULT_SIGNAL_BACKEND);
    apiService.setLegacyBackend(DEFAULT_LEGACY_BACKEND);
    setSaved(true);
    refresh();
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D]">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400">
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-black text-white font-mono uppercase">
              API Endpoints & Device ID
            </h2>
            <p className="text-xs text-slate-400">
              Railway Deployment Configurations
            </p>
          </div>
        </div>
      </div>

      <form onSubmit={handleSave} className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-4 font-mono text-xs">
        <div>
          <label className="text-slate-300 block mb-1 font-bold">
            Signal Backend URL (Railway)
          </label>
          <input
            type="url"
            value={signalUrl}
            onChange={e => setSignalUrl(e.target.value)}
            className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-cyan-400 font-mono text-xs focus:outline-none focus:border-cyan-400"
            required
          />
          <span className="text-[10px] text-slate-500 mt-1 block">
            Serves signals, market quotes, option chains, and Angel One session
          </span>
        </div>

        <div>
          <label className="text-slate-300 block mb-1 font-bold">
            Legacy / Chat Intelligence Backend URL
          </label>
          <input
            type="url"
            value={legacyUrl}
            onChange={e => setLegacyUrl(e.target.value)}
            className="w-full p-2.5 rounded-xl bg-[#070B12] border border-[#1C2740] text-slate-300 font-mono text-xs focus:outline-none focus:border-cyan-400"
            required
          />
        </div>

        <div className="p-3 rounded-xl bg-[#070B12] border border-[#1C2740] space-y-1">
          <div className="text-[10px] text-slate-400">Scoped Android Device ID (X-Device-Id)</div>
          <div className="text-xs font-bold text-white break-all">{deviceId}</div>
          <div className="text-[9px] text-slate-500">
            Persisted locally. Identifies this Android device to server-side broker stream.
          </div>
        </div>

        <div className="flex items-center space-x-2 pt-2">
          <button
            type="submit"
            className="flex-1 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#070B12] font-black text-xs flex items-center justify-center space-x-1.5 active:scale-95 transition-all shadow-md shadow-cyan-500/20"
          >
            {saved ? <Check className="w-4 h-4" /> : <Link2 className="w-4 h-4" />}
            <span>{saved ? 'SAVED SUCCESSFULLY' : 'SAVE CONFIGURATION'}</span>
          </button>

          <button
            type="button"
            onClick={handleReset}
            className="py-2.5 px-4 rounded-xl bg-[#17223B] hover:bg-[#1E2C4D] text-slate-300 font-bold text-xs active:scale-95 transition-all border border-[#1C2740]"
          >
            RESET
          </button>
        </div>
      </form>
    </div>
  );
};
