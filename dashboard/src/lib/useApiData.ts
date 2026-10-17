import { useEffect, useState } from "react";
import { startFetch, type Settled } from "./startFetch";

/** Everything the fetcher depends on, spelled out. Primitives only, so the key is stable and comparable. */
export type QueryKey = readonly (string | number | boolean | null)[];

/**
 * Fetches when `queryKey` changes. The fetcher receives an AbortSignal: the in-flight request is aborted when the
 * key changes or the component unmounts. Results are tagged with the key they were fetched for, so data from a
 * previous selection (e.g. the previously selected repo) is never returned while a new fetch is in flight.
 *
 * Contract: the fetcher may only depend on values listed in `queryKey` (it is not re-created into the effect).
 */
export function useApiData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  queryKey: QueryKey,
): {
  data: T | null;
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
  reload: () => void;
} {
  const key = JSON.stringify(queryKey);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<Settled<T> | null>(null);

  // The fetcher is deliberately not a dependency (callers pass a fresh closure every render); `key` is.
  // (react-hooks/exhaustive-deps is disabled project-wide in .oxlintrc.json - see DEVELOPER_GUIDE.md.)
  useEffect(() => startFetch(fetcher, key, attempt, setState), [key, attempt]);

  const current = state && state.key === key && state.attempt === attempt ? state : null;
  return {
    data: current?.data ?? null,
    loading: current === null,
    error: current?.error?.message ?? null,
    errorStatus: current?.error?.status ?? null,
    reload: () => setAttempt((a) => a + 1),
  };
}
