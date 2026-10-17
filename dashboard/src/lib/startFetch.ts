// React-free core of useApiData, so the cancellation / race rules can be unit-tested with `node --test`.
import { ApiError } from "./http.ts";

export interface Settled<T> {
  key: string;
  attempt: number;
  data?: T;
  error?: { message: string; status: number | null };
}

/**
 * Runs `fetcher` with an AbortSignal and reports the outcome via `onSettle` - unless the returned cancel function
 * was called first. A cancelled fetch aborts the in-flight request and can never report, even if its promise
 * resolves or rejects later (or the fetcher ignores the signal).
 */
export function startFetch<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  key: string,
  attempt: number,
  onSettle: (s: Settled<T>) => void,
): () => void {
  const ctrl = new AbortController();
  // `new Promise` also turns a synchronous throw inside fetcher into a rejection
  new Promise<T>((resolve) => resolve(fetcher(ctrl.signal)))
    .then((data) => {
      if (!ctrl.signal.aborted) onSettle({ key, attempt, data });
    })
    .catch((e) => {
      if (ctrl.signal.aborted) return;
      onSettle({
        key,
        attempt,
        error: {
          message: e instanceof Error ? e.message : String(e),
          status: e instanceof ApiError ? e.status : null,
        },
      });
    });
  return () => ctrl.abort();
}
