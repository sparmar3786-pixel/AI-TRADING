import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  FileText,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
} from "lucide-react";
import { getSignal } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import type { Signal } from "../types";
import { ErrorState, SentimentBadge, Spinner } from "../components/ui";

// Semicircular gauge drawn with a normalized SVG arc (pathLength=100), so the
// foreground stroke-dasharray maps 1:1 to a percentage. No chart library.
function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 75 ? "var(--bullish)" : pct >= 50 ? "var(--primary)" : "var(--neutral)";
  const arc = "M 20 100 A 80 80 0 0 1 180 100";
  return (
    <div className="relative flex flex-col items-center">
      <svg viewBox="0 0 200 120" className="w-48">
        <path
          d={arc}
          fill="none"
          stroke="var(--border)"
          strokeWidth={14}
          strokeLinecap="round"
        />
        <path
          d={arc}
          fill="none"
          stroke={color}
          strokeWidth={14}
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={`${pct} 100`}
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
      </svg>
      <div className="-mt-12 flex flex-col items-center">
        <span className="text-4xl font-semibold tabular-nums" style={{ color }}>
          {pct}%
        </span>
        <span className="stat-label mt-1">Confidence</span>
      </div>
    </div>
  );
}

function BeatBadge({ value }: { value: boolean | null | undefined }) {
  if (value === true)
    return <span className="font-semibold text-[var(--bullish)]">Beat</span>;
  if (value === false)
    return <span className="font-semibold text-[var(--bearish)]">Miss</span>;
  return <span className="text-[var(--text-muted)]">N/A</span>;
}

function MetricCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="stat-label">{label}</div>
      <div className="mt-2 text-lg capitalize">{children}</div>
    </div>
  );
}

export default function SignalDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const signalId = Number(id);

  const { data, loading, error, reload } = useFetch<Signal>(
    () => getSignal(signalId),
    [signalId],
  );

  if (loading) return <Spinner />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <ErrorState message="Signal not found." />;

  const km = data.key_metrics;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-sm text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      {/* Header */}
      <div className="card flex flex-col gap-6 p-6 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">{data.ticker}</h1>
            <span className="text-sm text-[var(--text-muted)]">{data.filing_date}</span>
          </div>
          <div className="flex items-center gap-3">
            <SentimentBadge sentiment={data.sentiment} size="lg" />
            <span className="pill bg-[var(--surface-hover)] capitalize text-[var(--text-muted)]">
              Tone: {data.management_tone ?? "n/a"}
            </span>
            {data.llm_model && (
              <span className="font-mono text-xs text-[var(--text-muted)]">
                {data.llm_model}
              </span>
            )}
          </div>
        </div>
        <ConfidenceGauge value={data.confidence} />
      </div>

      {/* Bull / Bear */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card border-l-4 border-l-[var(--bullish)] p-5">
          <div className="flex items-center gap-2 text-[var(--bullish)]">
            <TrendingUp className="h-4 w-4" />
            <h2 className="text-sm font-semibold">Bull Case</h2>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-[var(--text-primary)]">
            {data.bull_case || "n/a"}
          </p>
        </div>
        <div className="card border-l-4 border-l-[var(--bearish)] p-5">
          <div className="flex items-center gap-2 text-[var(--bearish)]">
            <TrendingDown className="h-4 w-4" />
            <h2 className="text-sm font-semibold">Bear Case</h2>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-[var(--text-primary)]">
            {data.bear_case || "n/a"}
          </p>
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard label="EPS vs Estimate">
          <BeatBadge value={km.eps_beat} />
        </MetricCard>
        <MetricCard label="Revenue vs Estimate">
          <BeatBadge value={km.revenue_beat} />
        </MetricCard>
        <MetricCard label="Forward Guidance">
          {data.guidance_quality ?? "n/a"}
        </MetricCard>
      </div>

      {/* Risk flags */}
      <div className="card p-5">
        <div className="flex items-center gap-2 text-[var(--text-primary)]">
          <ShieldAlert className="h-4 w-4 text-[#f59e0b]" />
          <h2 className="text-sm font-semibold">Risk Flags</h2>
        </div>
        {data.risk_flags.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {data.risk_flags.map((flag, i) => (
              <span
                key={i}
                className="pill border border-[rgba(245,158,11,0.3)] bg-[rgba(245,158,11,0.1)] text-[#f59e0b]"
              >
                {flag}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-sm text-[var(--text-muted)]">No risk flags identified.</p>
        )}
      </div>

      {/* Reasoning */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold">Reasoning</h2>
        <p className="mt-3 text-sm leading-relaxed text-[var(--text-primary)]">
          {data.reasoning || "n/a"}
        </p>
      </div>

      {/* View raw filing */}
      <div>
        <button
          onClick={() => navigate(`/filings?open=${data.filing_id}`)}
          className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-medium transition-colors hover:bg-[var(--surface-hover)]"
        >
          <FileText className="h-4 w-4 text-[var(--primary)]" />
          View Raw Filing
        </button>
      </div>
    </div>
  );
}
