import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, ChevronDown } from "lucide-react";
import { getSignals, getStats } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import type { Signal, Stats } from "../types";
import {
  ConfidenceBar,
  ErrorState,
  SentimentBadge,
  Spinner,
} from "../components/ui";

export default function Signals() {
  const navigate = useNavigate();
  const [ticker, setTicker] = useState<string>("");

  const statsState = useFetch<Stats>(() => getStats(), []);
  const signalsState = useFetch<Signal[]>(
    () => getSignals(ticker || undefined, 200),
    [ticker],
  );

  const tickers = statsState.data?.analyzed_tickers ?? [];
  const signals = signalsState.data ?? [];

  return (
    <div className="space-y-5">
      {/* Filter bar */}
      <div className="flex items-center justify-between">
        <div className="relative">
          <select
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="appearance-none rounded-lg border border-[var(--border)] bg-[var(--surface)] py-2 pl-3 pr-9 text-sm text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--surface-hover)] focus:border-[var(--primary)]"
          >
            <option value="">All tickers</option>
            {tickers.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
        </div>
        <span className="text-xs text-[var(--text-muted)]">
          {signals.length} signal{signals.length === 1 ? "" : "s"}
        </span>
      </div>

      {signalsState.loading ? (
        <Spinner />
      ) : signalsState.error ? (
        <ErrorState message={signalsState.error} onRetry={signalsState.reload} />
      ) : signals.length === 0 ? (
        <div className="card flex flex-col items-center justify-center gap-2 py-16 text-center text-sm text-[var(--text-muted)]">
          <AlertCircle className="h-8 w-8 opacity-50" />
          No signals found{ticker ? ` for ${ticker}` : ""}.
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-[var(--text-muted)]">
                <th className="px-5 py-3 font-medium">Ticker</th>
                <th className="px-5 py-3 font-medium">Date</th>
                <th className="px-5 py-3 font-medium">Sentiment</th>
                <th className="px-5 py-3 font-medium">Confidence</th>
                <th className="px-5 py-3 font-medium">Guidance</th>
                <th className="px-5 py-3 font-medium">Tone</th>
                <th className="px-5 py-3 font-medium">Risks</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => navigate(`/signals/${s.id}`)}
                  className="cursor-pointer border-t border-[var(--border)] card-hover"
                >
                  <td className="px-5 py-3 font-semibold">{s.ticker}</td>
                  <td className="px-5 py-3 text-[var(--text-muted)]">{s.filing_date}</td>
                  <td className="px-5 py-3">
                    <SentimentBadge sentiment={s.sentiment} />
                  </td>
                  <td className="px-5 py-3">
                    <ConfidenceBar value={s.confidence} />
                  </td>
                  <td className="px-5 py-3 capitalize text-[var(--text-muted)]">
                    {s.guidance_quality ?? "n/a"}
                  </td>
                  <td className="px-5 py-3 capitalize text-[var(--text-muted)]">
                    {s.management_tone ?? "n/a"}
                  </td>
                  <td className="px-5 py-3">
                    <span className="pill bg-[rgba(239,68,68,0.1)] text-[var(--bearish)]">
                      {s.risk_flags.length}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
