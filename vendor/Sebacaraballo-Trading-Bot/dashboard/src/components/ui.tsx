// Small reusable presentational components shared across pages:
// loading spinner, error state with retry, sentiment badge, confidence bar.

import { Loader2, AlertTriangle, TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { Sentiment } from "../types";

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-[var(--text-muted)]">
      <Loader2 className="h-7 w-7 animate-spin text-[var(--primary)]" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-4 text-center">
      <AlertTriangle className="h-8 w-8 text-[var(--bearish)]" />
      <div className="max-w-md text-sm text-[var(--text-muted)]">{message}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
        >
          Retry
        </button>
      )}
    </div>
  );
}

const SENTIMENT_STYLES: Record<
  Sentiment,
  { color: string; bg: string; label: string }
> = {
  bullish: { color: "var(--bullish)", bg: "rgba(34,197,94,0.12)", label: "Bullish" },
  bearish: { color: "var(--bearish)", bg: "rgba(239,68,68,0.12)", label: "Bearish" },
  neutral: { color: "var(--neutral)", bg: "rgba(148,163,184,0.12)", label: "Neutral" },
};

export function SentimentBadge({
  sentiment,
  size = "sm",
}: {
  sentiment: Sentiment;
  size?: "sm" | "lg";
}) {
  const s = SENTIMENT_STYLES[sentiment] ?? SENTIMENT_STYLES.neutral;
  const Icon =
    sentiment === "bullish" ? TrendingUp : sentiment === "bearish" ? TrendingDown : Minus;
  const pad = size === "lg" ? "px-3 py-1.5 text-sm" : "px-2.5 py-0.5 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${pad}`}
      style={{ color: s.color, backgroundColor: s.bg }}
    >
      <Icon className={size === "lg" ? "h-4 w-4" : "h-3 w-3"} />
      {s.label}
    </span>
  );
}

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 75 ? "var(--bullish)" : pct >= 50 ? "var(--primary)" : "var(--neutral)";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-[var(--border)]">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-9 text-right text-xs tabular-nums text-[var(--text-muted)]">
        {pct}%
      </span>
    </div>
  );
}

export function formatBytes(chars: number): string {
  if (chars < 1000) return `${chars} ch`;
  return `${(chars / 1000).toFixed(1)}k ch`;
}
