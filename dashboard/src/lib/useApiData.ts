import { useEffect, useState } from "react";

export function useApiData<T>(fetcher: () => Promise<T>, deps: unknown[]): {
  data: T | null;
  loading: boolean;
  error: string | null;
} {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `fetcher` is intentionally excluded from deps: callers pass a fresh
    // closure each render, and re-running on that would defeat the point of
    // `deps`, which callers set explicitly to the values that should
    // actually trigger a refetch. (react-hooks/exhaustive-deps disabled
    // project-wide in .oxlintrc.json - see DEVELOPER_GUIDE.md for why.)
  }, deps);

  return { data, loading, error };
}
