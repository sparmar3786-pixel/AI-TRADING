import React from 'react';
import { useTrading } from '../context/TradingContext';
import { Cpu, Server, Radio, Database, CheckCircle, RefreshCw } from 'lucide-react';

export const DataHealthPage: React.FC = () => {
  const { diagnostics, isLive, marketStatus, refresh, isRefreshing } = useTrading();

  const worker = diagnostics?.backend_worker;
  const angel = diagnostics?.angel_one;
  const data = diagnostics?.market_data;
  const ai = diagnostics?.ai_provider;
  const workerStatus = !worker ? 'UNKNOWN / NOT TESTED' : worker.cycle_fresh ? 'HEALTHY' : 'STALE';
  const angelStatus = !angel ? 'UNKNOWN / NOT TESTED' : angel.authenticated ? 'AUTHENTICATED' : 'NOT AUTHENTICATED';
  const aiStatus = !ai ? 'UNKNOWN / NOT TESTED' : ai.configured ? 'CONFIGURED' : 'NOT CONFIGURED';

  return (
    <div className="p-3 pb-8 space-y-4 select-none max-w-2xl mx-auto">
      {/* Top Banner */}
      <div className="card-base p-4 border border-[#1C2740] bg-[#121A2D] flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-400">
            <Cpu className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-sm font-black text-white font-mono uppercase">
              System & Telemetry Health
            </h2>
            <p className="text-xs text-slate-400">
              Railway Engine • Broker Stream • Instrument Ticks
            </p>
          </div>
        </div>

        <button
          onClick={() => refresh()}
          disabled={isRefreshing}
          className="p-2 rounded-xl bg-[#17223B] text-cyan-400 hover:bg-[#1E2C4D] active:scale-95 transition-all"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Health Metric Cards */}
      <div className="space-y-3 font-mono">
        {/* Backend Worker */}
        <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2 text-white font-bold">
              <Server className="w-4 h-4 text-cyan-400" />
              <span>Railway Algo Backend Worker</span>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 font-bold">
              {workerStatus}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-xs pt-1">
            <div className="p-2 rounded-lg bg-[#070B12]">
              <div className="text-[9px] text-slate-500">CYCLE AGE</div>
              <div className="font-bold text-white mt-0.5">{worker?.cycle_age_seconds ?? '—'}s ago</div>
            </div>
            <div className="p-2 rounded-lg bg-[#070B12]">
              <div className="text-[9px] text-slate-500">CYCLE FRESH</div>
              <div className="font-bold text-emerald-400 mt-0.5">{worker ? (worker.cycle_fresh ? 'YES' : 'NO') : 'UNKNOWN'}</div>
            </div>
            <div className="p-2 rounded-lg bg-[#070B12]">
              <div className="text-[9px] text-slate-500">UPTIME</div>
              <div className="font-bold text-white mt-0.5">{worker?.uptime_hours ?? '—'} hrs</div>
            </div>
          </div>
        </div>

        {/* Angel One Broker Stream */}
        <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2 text-white font-bold">
              <Radio className="w-4 h-4 text-emerald-400" />
              <span>Angel One Broker Session</span>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 font-bold">
              {angelStatus}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-xs pt-1">
            <div className="p-2 rounded-lg bg-[#070B12]">
              <div className="text-[9px] text-slate-500">WEBSOCKET</div>
              <div className="font-bold text-emerald-400 mt-0.5">{angel ? (angel.stream_open ? 'OPEN' : 'CLOSED') : 'UNKNOWN'}</div>
            </div>
            <div className="p-2 rounded-lg bg-[#070B12]">
              <div className="text-[9px] text-slate-500">LAST TICK</div>
              <div className="font-bold text-white mt-0.5">{angel?.last_tick_age_seconds ?? '—'}s</div>
            </div>
            <div className="p-2 rounded-lg bg-[#070B12]">
              <div className="text-[9px] text-slate-500">CLIENT CODE</div>
              <div className="font-bold text-cyan-400 mt-0.5">{angel?.client_code ?? 'Not verified'}</div>
            </div>
          </div>
        </div>

        {/* Market Data Pipeline */}
        <div className="card-base p-4 border border-[#1C2740] bg-[#101726] space-y-2">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2 text-white font-bold">
              <Database className="w-4 h-4 text-purple-400" />
              <span>Tick Pipeline & Instruments</span>
            </div>
            <span className="text-[10px] text-slate-400">
              {data?.ticks_per_second ?? '—'} ticks/sec
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-center text-xs pt-1">
            <div className="p-2 rounded-lg bg-[#070B12]">
              <div className="text-[9px] text-slate-500">TOTAL SNAPSHOTS</div>
              <div className="font-bold text-white mt-0.5">{data?.snapshot_count ?? '—'}</div>
            </div>
            <div className="p-2 rounded-lg bg-[#070B12]">
              <div className="text-[9px] text-slate-500">FRESH SNAPSHOTS</div>
              <div className="font-bold text-emerald-400 mt-0.5">{data?.fresh_snapshot_count ?? '—'}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
