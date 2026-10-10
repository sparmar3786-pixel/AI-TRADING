import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import {
  ApiError,
  isSnapshotFallbackActive,
  subscribeSnapshotFallback,
} from "./api";

// True once any request fell back from a configured live API to the bundled
// snapshot. Drives the header's "cached data" badge.
export function useSnapshotFallback(): boolean {
  return useSyncExternalStore(subscribeSnapshotFallback, isSnapshotFallbackActive);
}

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

// Generic data-fetching hook: tracks loading/error and exposes a reload()
// for the retry buttons. `deps` re-runs the fetch when they change.
export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: ReadonlyArray<unknown> = [],
): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    run()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Something went wrong while loading data.";
        setError(message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run]);

  useEffect(() => {
    const cleanup = load();
    return cleanup;
  }, [load]);

  return { data, loading, error, reload: load };
}
