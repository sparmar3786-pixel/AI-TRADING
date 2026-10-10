import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  CartesianGrid,
  Tooltip,
} from "recharts";
import {
  TrendingUp,
  Activity,
  Percent,
  ArrowDownRight,
  Lock,
  ArrowUpDown,
} from "lucide-react";
import { getLatestBacktest } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import type { BacktestResults, BacktestTrade } from "../types";
import { ErrorState, Spinner } from "../components/ui";

const START_CAPITAL = 10_000;

function pct(v: number, signed = true): string {
  const s = (v * 100).toFixed(1);
  return signed && v >= 0 ? `+${s}%` : `${s}%`;
}

function StatCard({
  label,
  value,
  color,
  icon: Icon,
  sub,
}: {
  label: string;
  value: string;
  color?: string;
  icon: typeof Activity;
  sub?: string;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between">
        <span className="stat-label">{label}</span>
        <Icon className="h-4 w-4 text-[var(--text-muted)]" />
      </div>
      <div
        className="mt-3 text-3xl font-semibold tabular-nums tracking-tight"
        style={color ? { color } : undefined}
      >
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-[var(--text-muted)]">{sub}</div>}
    </div>
  );
}

function StatsRow({ data }: { data: BacktestResults }) {
  const winColor = data.win_rate > 0.5 ? "var(--bullish)" : "var(--text-primary)";
  const sharpeColor =
    data.sharpe_ratio > 1.0
      ? "var(--bullish)"
      : data.sharpe_ratio >= 0.5
        ? "#f59e0b"
        : "var(--bearish)";
  const beat = data.total_return_pct > data.spy_return_pct;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Win Rate"
        value={pct(data.win_rate, false)}
        color={winColor}
        icon={Percent}
        sub={`${data.trades_executed} trades`}
      />
      <StatCard
        label="Sharpe Ratio"
        value={data.sharpe_ratio.toFixed(2)}
        color={sharpeColor}
        icon={Activity}
        sub="annualized, 5-day hold"
      />
      <StatCard
        label="Max Drawdown"
        value={pct(data.max_drawdown_pct)}
        color="var(--bearish)"
        icon={ArrowDownRight}
      />
      <StatCard
        label="vs. SPY"
        value={pct(data.total_return_pct)}
        color={beat ? "var(--bullish)" : "var(--bearish)"}
        icon={TrendingUp}
        sub={`${pct(data.total_return_pct)} vs ${pct(data.spy_return_pct)} SPY`}
      />
    </div>
  );
}

// The full honest metrics table, including the SPY benchmark the strategy
// trails. Numbers must match the README and the seeded dataset exactly.
function SummaryTable({ data }: { data: BacktestResults }) {
  const returnColor = (v: number) =>
    v >= 0 ? "var(--bullish)" : "var(--bearish)";
  const rows: { label: string; value: string; color?: string }[] = [
    { label: "Trades", value: String(data.trades_executed) },
    { label: "Win rate", value: pct(data.win_rate, false) },
    {
      label: "Avg return per trade",
      value: pct(data.avg_return_pct),
      color: returnColor(data.avg_return_pct),
    },
    {
      label: "Total return",
      value: pct(data.total_return_pct),
      color: returnColor(data.total_return_pct),
    },
    {
      label: "SPY benchmark (same period)",
      value: pct(data.spy_return_pct),
      color: returnColor(data.spy_return_pct),
    },
    { label: "Sharpe ratio (annualized, 5-day hold)", value: data.sharpe_ratio.toFixed(2) },
    {
      label: "Max drawdown",
      value: pct(data.max_drawdown_pct),
      color: "var(--bearish)",
    },
  ];

  return (
    <div className="card overflow-hidden">
      <div className="border-b border-[var(--border)] px-5 py-4">
        <h2 className="text-sm font-semibold">Performance Summary</h2>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-[var(--border)] first:border-t-0">
              <td className="px-5 py-3 text-[var(--text-muted)]">{row.label}</td>
              <td
                className="px-5 py-3 text-right font-medium tabular-nums"
                style={row.color ? { color: row.color } : undefined}
              >
                {row.value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-[var(--border)] px-5 py-4 text-xs leading-relaxed text-[var(--text-muted)]">
        Naive equal-weight sizing produces the drawdown shown. Current work:
        transaction-cost modeling and Kelly-criterion position sizing.
      </p>
    </div>
  );
}

function EquityChart({ data }: { data: BacktestResults }) {
  return (
    <div className="card p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Portfolio Value</h2>
        <span className="text-xs text-[var(--text-muted)]">
          Starting capital ${START_CAPITAL.toLocaleString()}
        </span>
      </div>
      <div className="mt-4 h-[280px]">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data.equity_curve} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="var(--text-muted)"
              tick={{ fontSize: 11 }}
              minTickGap={40}
            />
            <YAxis
              stroke="var(--text-muted)"
              tick={{ fontSize: 11 }}
              width={56}
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                color: "var(--text-primary)",
              }}
              formatter={(value) => [`$${Number(value).toLocaleString()}`, "Value"]}
              labelStyle={{ color: "var(--text-muted)" }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function TradesTable({ trades }: { trades: BacktestTrade[] }) {
  const [desc, setDesc] = useState(true);
  const [showAll, setShowAll] = useState(false);

  const sorted = useMemo(() => {
    const copy = [...trades].sort((a, b) =>
      desc ? b.return_pct - a.return_pct : a.return_pct - b.return_pct,
    );
    return copy;
  }, [trades, desc]);

  const visible = showAll ? sorted : sorted.slice(0, 20);

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
        <h2 className="text-sm font-semibold">
          Trades <span className="text-[var(--text-muted)]">({trades.length})</span>
        </h2>
        {trades.length > 20 && (
          <button
            onClick={() => setShowAll((s) => !s)}
            className="text-xs text-[var(--primary)] hover:underline"
          >
            {showAll ? "Show top 20" : `Show all ${trades.length}`}
          </button>
        )}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-[var(--text-muted)]">
            <th className="px-5 py-2 font-medium">Ticker</th>
            <th className="px-5 py-2 font-medium">Entry Date</th>
            <th className="px-5 py-2 font-medium">Exit Date</th>
            <th className="px-5 py-2 font-medium">Entry Price</th>
            <th className="px-5 py-2 font-medium">Exit Price</th>
            <th className="px-5 py-2 font-medium">
              <button
                onClick={() => setDesc((d) => !d)}
                className="inline-flex items-center gap-1 hover:text-[var(--text-primary)]"
                title="Sort by return"
              >
                Return <ArrowUpDown className="h-3 w-3" />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {visible.map((t) => {
            const positive = t.return_pct >= 0;
            return (
              <tr
                key={t.signal_id}
                className="border-t border-[var(--border)] card-hover"
              >
                <td className="px-5 py-3 font-semibold">{t.ticker}</td>
                <td className="px-5 py-3 text-[var(--text-muted)]">{t.entry_date}</td>
                <td className="px-5 py-3 text-[var(--text-muted)]">{t.exit_date}</td>
                <td className="px-5 py-3 tabular-nums">${t.entry_price.toFixed(2)}</td>
                <td className="px-5 py-3 tabular-nums">${t.exit_price.toFixed(2)}</td>
                <td
                  className="px-5 py-3 font-medium tabular-nums"
                  style={{ color: positive ? "var(--bullish)" : "var(--bearish)" }}
                >
                  {pct(t.return_pct)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// Shown when no backtest has been run yet (API returns 404 → null).
function NotRunPlaceholder() {
  const PLACEHOLDER_CURVE = Array.from({ length: 24 }, (_, i) => ({
    t: i,
    v: 100000 + Math.sin(i / 2.5) * 6000 + i * 1400,
  }));
  const PLACEHOLDER_STATS = [
    { label: "Win Rate", icon: Percent },
    { label: "Sharpe Ratio", icon: Activity },
    { label: "Max Drawdown", icon: ArrowDownRight },
    { label: "Total Return", icon: TrendingUp },
  ];
  return (
    <div className="relative">
      <div className="pointer-events-none select-none space-y-6 opacity-40 blur-[1.5px]">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PLACEHOLDER_STATS.map((s) => (
            <div key={s.label} className="card p-5">
              <div className="flex items-start justify-between">
                <span className="stat-label">{s.label}</span>
                <s.icon className="h-4 w-4 text-[var(--text-muted)]" />
              </div>
              <div className="mt-3 h-8 w-20 animate-pulse rounded-md bg-[var(--surface-hover)]" />
            </div>
          ))}
        </div>
        <div className="card p-5">
          <h2 className="text-sm font-semibold">Portfolio Value</h2>
          <div className="mt-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={PLACEHOLDER_CURVE}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="t" stroke="var(--text-muted)" tick={false} />
                <YAxis stroke="var(--text-muted)" tick={false} width={20} />
                <Line type="monotone" dataKey="v" stroke="var(--primary)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="card max-w-md p-8 text-center shadow-2xl">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--surface-hover)]">
            <Lock className="h-5 w-5 text-[var(--text-muted)]" />
          </div>
          <h2 className="mt-4 text-lg font-semibold">Backtest not run yet</h2>
          <p className="mt-2 text-sm text-[var(--text-muted)]">
            Replay stored signals against historical prices to produce an equity
            curve, risk stats, and a trade ledger.
          </p>
          <div className="mt-5 rounded-lg border border-[var(--border)] bg-[var(--bg)] px-4 py-3 text-left">
            <span className="stat-label">Run it</span>
            <code className="mt-1 block font-mono text-sm text-[var(--primary)]">
              python main.py --backtest
            </code>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Backtest() {
  const { data, loading, error, reload } = useFetch<BacktestResults | null>(
    () => getLatestBacktest(),
    [],
  );

  if (loading) return <Spinner />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data || data.trades_executed === 0) return <NotRunPlaceholder />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--text-muted)]">
          Run {data.run_date?.replace("T", " ")} · signals ≥{" "}
          {Math.round(data.confidence_threshold * 100)}% confidence · since{" "}
          {data.start_date}
        </p>
      </div>
      <StatsRow data={data} />
      <SummaryTable data={data} />
      <EquityChart data={data} />
      <TradesTable trades={data.trades} />
    </div>
  );
}
