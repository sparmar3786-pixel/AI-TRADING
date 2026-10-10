import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  Building2,
  FileText,
  Zap,
  Gauge,
  ArrowUpRight,
} from "lucide-react";
import { getSignals, getStats } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import type { Sentiment, Signal, Stats } from "../types";
import {
  ConfidenceBar,
  ErrorState,
  SentimentBadge,
  Spinner,
} from "../components/ui";

const SENTIMENT_COLORS: Record<Sentiment, string> = {
  bullish: "#22c55e",
  neutral: "#94a3b8",
  bearish: "#ef4444",
};

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: typeof Building2;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between">
        <span className="stat-label">{label}</span>
        <Icon className="h-4 w-4 text-[var(--text-muted)]" />
      </div>
      <div className="mt-3 text-3xl font-semibold tabular-nums tracking-tight">
        {value}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <Zap className="h-10 w-10 text-[var(--text-muted)] opacity-50" />
      <p className="text-sm text-[var(--text-muted)]">
        No signals yet. Run{" "}
        <code className="rounded bg-[var(--bg)] px-1.5 py-0.5 font-mono text-[var(--primary)]">
          python main.py AAPL --analyze
        </code>{" "}
        to generate your first signal.
      </p>
    </div>
  );
}

export default function Overview() {
  const navigate = useNavigate();
  const statsState = useFetch<Stats>(() => getStats(), []);
  // Fetch the full signal set so avg confidence and the sentiment split
  // describe the whole dataset; the table below shows the 10 most recent.
  const signalsState = useFetch<Signal[]>(() => getSignals(undefined, 200), []);

  const stats = statsState.data;
  const signals = signalsState.data ?? [];
  const recentSignals = signals.slice(0, 10);

  const avgConfidence = useMemo(() => {
    if (!signals.length) return 0;
    return signals.reduce((sum, s) => sum + s.confidence, 0) / signals.length;
  }, [signals]);

  const distribution = useMemo(() => {
    const counts: Record<Sentiment, number> = { bullish: 0, neutral: 0, bearish: 0 };
    for (const s of signals) counts[s.sentiment] = (counts[s.sentiment] ?? 0) + 1;
    return (Object.keys(counts) as Sentiment[])
      .map((k) => ({ name: k, value: counts[k] }))
      .filter((d) => d.value > 0);
  }, [signals]);

  if (statsState.loading || signalsState.loading) return <Spinner />;
  if (statsState.error)
    return <ErrorState message={statsState.error} onRetry={statsState.reload} />;
  if (signalsState.error)
    return <ErrorState message={signalsState.error} onRetry={signalsState.reload} />;

  return (
    <div className="space-y-6">
      {/* Stats row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Companies Tracked" value={stats?.companies ?? 0} icon={Building2} />
        <StatCard label="Filings Stored" value={stats?.filings ?? 0} icon={FileText} />
        <StatCard label="Signals Generated" value={stats?.signals ?? 0} icon={Zap} />
        <StatCard
          label="Avg Confidence"
          value={signals.length ? `${Math.round(avgConfidence * 100)}%` : "n/a"}
          icon={Gauge}
        />
      </div>

      {signals.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Sentiment distribution */}
          <div className="card p-5 lg:col-span-1">
            <h2 className="text-sm font-semibold">Sentiment Distribution</h2>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">
              Across all {signals.length} signal{signals.length === 1 ? "" : "s"}
            </p>
            <div className="mt-4 h-[260px]">
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={distribution}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={3}
                    stroke="none"
                  >
                    {distribution.map((d) => (
                      <Cell key={d.name} fill={SENTIMENT_COLORS[d.name as Sentiment]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "var(--surface)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      color: "var(--text-primary)",
                      textTransform: "capitalize",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 flex justify-center gap-4">
              {distribution.map((d) => (
                <div key={d.name} className="flex items-center gap-1.5 text-xs">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: SENTIMENT_COLORS[d.name as Sentiment] }}
                  />
                  <span className="capitalize text-[var(--text-muted)]">{d.name}</span>
                  <span className="tabular-nums">{d.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Recent signals table */}
          <div className="card lg:col-span-2">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
              <h2 className="text-sm font-semibold">Recent Signals</h2>
              <button
                onClick={() => navigate("/signals")}
                className="flex items-center gap-1 text-xs text-[var(--primary)] hover:underline"
              >
                View all <ArrowUpRight className="h-3 w-3" />
              </button>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-[var(--text-muted)]">
                  <th className="px-5 py-2 font-medium">Ticker</th>
                  <th className="px-5 py-2 font-medium">Date</th>
                  <th className="px-5 py-2 font-medium">Sentiment</th>
                  <th className="px-5 py-2 font-medium">Confidence</th>
                  <th className="px-5 py-2 font-medium">Guidance</th>
                </tr>
              </thead>
              <tbody>
                {recentSignals.map((s) => (
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
