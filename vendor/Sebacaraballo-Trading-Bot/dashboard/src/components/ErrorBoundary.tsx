import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

// Last line of defense: an unexpected render error (bad data shape, library
// throw) shows a styled recovery screen instead of a white page.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled render error:", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-[var(--bg)] px-6 text-center text-[var(--text-primary)]">
        <AlertTriangle className="h-10 w-10 text-[var(--bearish)]" />
        <h1 className="text-lg font-semibold">Something went wrong</h1>
        <p className="max-w-md text-sm text-[var(--text-muted)]">
          The dashboard hit an unexpected error while rendering. Reloading
          usually fixes it.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-medium transition-colors hover:bg-[var(--surface-hover)]"
        >
          Reload dashboard
        </button>
      </div>
    );
  }
}
