import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  BarChart2,
  Zap,
  FileText,
  TrendingUp,
  Briefcase,
  DatabaseZap,
} from "lucide-react";
import type { ComponentType } from "react";
import { useSnapshotFallback } from "./lib/useFetch";
import Overview from "./pages/Overview";
import Signals from "./pages/Signals";
import SignalDetail from "./pages/SignalDetail";
import Filings from "./pages/Filings";
import Backtest from "./pages/Backtest";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: BarChart2 },
  { to: "/signals", label: "Signals", icon: Zap },
  { to: "/filings", label: "Filings", icon: FileText },
  { to: "/backtest", label: "Backtest", icon: TrendingUp },
  { to: "/portfolio", label: "Portfolio", icon: Briefcase },
];

// Map the current pathname to a human page title for the header bar.
function titleForPath(pathname: string): string {
  if (pathname === "/") return "Overview";
  if (pathname.startsWith("/signals")) return "Signals";
  if (pathname.startsWith("/filings")) return "Filings";
  if (pathname.startsWith("/backtest")) return "Backtest";
  if (pathname.startsWith("/portfolio")) return "Portfolio";
  return "Earnings Intelligence";
}

function Sidebar() {
  return (
    <aside className="flex w-16 flex-col items-center border-r border-[var(--border)] bg-[var(--surface)] py-4">
      <div className="mb-6 flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--primary)] text-sm font-bold tracking-tight text-white">
        EI
      </div>
      <nav className="flex flex-1 flex-col items-center gap-2">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            title={label}
            className={({ isActive }) =>
              `group relative flex h-11 w-11 items-center justify-center rounded-xl transition-colors ${
                isActive
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
              }`
            }
          >
            <Icon className="h-5 w-5" />
            <span className="pointer-events-none absolute left-14 z-10 whitespace-nowrap rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-xs text-[var(--text-primary)] opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
              {label}
            </span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

function Header({ title }: { title: string }) {
  const usingCachedData = useSnapshotFallback();
  const stamp = new Date().toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-[var(--border)] px-8">
      <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
      <div className="flex items-center gap-3">
        {usingCachedData && (
          <span
            title="The live API is unreachable. Showing the data snapshot bundled with this build."
            className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-muted)]"
          >
            <DatabaseZap className="h-3 w-3" />
            cached data
          </span>
        )}
        <div className="text-xs text-[var(--text-muted)]">
          Last updated <span className="text-[var(--text-primary)]">{stamp}</span>
        </div>
      </div>
    </header>
  );
}

// Placeholder for the Portfolio nav slot (Phase 4 / future).
function Portfolio() {
  return (
    <div className="flex h-96 flex-col items-center justify-center gap-2 text-center text-[var(--text-muted)]">
      <Briefcase className="h-10 w-10 opacity-40" />
      <p className="text-sm">Portfolio view arrives with Phase 4 (Alpaca paper trading).</p>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--text-primary)]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={titleForPath(location.pathname)} />
        <main className="flex-1 overflow-y-auto px-8 py-6">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/signals/:id" element={<SignalDetail />} />
            <Route path="/filings" element={<Filings />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/portfolio" element={<Portfolio />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
