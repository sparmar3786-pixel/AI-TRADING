import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Check, Minus, X, FileText, ChevronDown } from "lucide-react";
import { getFilings, getFilingText, getStats } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import type { Filing, FilingText, Stats } from "../types";
import { ErrorState, Spinner, formatBytes } from "../components/ui";

function FilingDrawer({
  filingId,
  onClose,
}: {
  filingId: number;
  onClose: () => void;
}) {
  const { data, loading, error, reload } = useFetch<FilingText>(
    () => getFilingText(filingId),
    [filingId],
  );

  return (
    <div className="fixed inset-0 z-30 flex justify-end">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative flex h-full w-full max-w-2xl flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-[var(--primary)]" />
            <h2 className="text-sm font-semibold">
              {data ? `${data.ticker} · ${data.filing_date}` : "Filing text"}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <Spinner label="Loading filing text…" />
          ) : error ? (
            <ErrorState message={error} onRetry={reload} />
          ) : (
            <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-[var(--text-muted)]">
              {data?.text || "(empty)"}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Filings() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [ticker, setTicker] = useState<string>("");
  const [openId, setOpenId] = useState<number | null>(null);

  const statsState = useFetch<Stats>(() => getStats(), []);
  const filingsState = useFetch<Filing[]>(
    () => getFilings(ticker || undefined, 200),
    [ticker],
  );

  // Honor the ?open=<filing_id> deep link from SignalDetail's "View Raw Filing".
  useEffect(() => {
    const open = searchParams.get("open");
    if (open) {
      setOpenId(Number(open));
      searchParams.delete("open");
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tickers = statsState.data?.analyzed_tickers ?? [];
  const filings = filingsState.data ?? [];

  return (
    <div className="space-y-5">
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
          {filings.length} filing{filings.length === 1 ? "" : "s"}
        </span>
      </div>

      {filingsState.loading ? (
        <Spinner />
      ) : filingsState.error ? (
        <ErrorState message={filingsState.error} onRetry={filingsState.reload} />
      ) : filings.length === 0 ? (
        <div className="card py-16 text-center text-sm text-[var(--text-muted)]">
          No filings stored{ticker ? ` for ${ticker}` : ""}.
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-[var(--text-muted)]">
                <th className="px-5 py-3 font-medium">Ticker</th>
                <th className="px-5 py-3 font-medium">Date</th>
                <th className="px-5 py-3 font-medium">Form</th>
                <th className="px-5 py-3 font-medium">Size</th>
                <th className="px-5 py-3 font-medium">Analyzed</th>
                <th className="px-5 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filings.map((f) => (
                <tr
                  key={f.id}
                  className={`border-t border-[var(--border)] ${
                    f.has_signal ? "bg-[rgba(99,102,241,0.06)]" : ""
                  }`}
                >
                  <td className="px-5 py-3 font-semibold">{f.ticker}</td>
                  <td className="px-5 py-3 text-[var(--text-muted)]">{f.filing_date}</td>
                  <td className="px-5 py-3 text-[var(--text-muted)]">{f.form_type}</td>
                  <td className="px-5 py-3 tabular-nums text-[var(--text-muted)]">
                    {formatBytes(f.text_length)}
                  </td>
                  <td className="px-5 py-3">
                    {f.has_signal ? (
                      <span className="inline-flex items-center gap-1 text-[var(--bullish)]">
                        <Check className="h-4 w-4" />
                      </span>
                    ) : (
                      <Minus className="h-4 w-4 text-[var(--text-muted)]" />
                    )}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => setOpenId(f.id)}
                      className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--surface-hover)]"
                    >
                      View Text
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openId !== null && (
        <FilingDrawer filingId={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}
