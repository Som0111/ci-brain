import type {
  BenchmarkResults,
  FlakinessReport,
  GraphSummary,
  ImpactResponse,
  Repo,
  TestRunSummary,
} from "./types";
import { ApiError, makeRequest } from "./http";

// Defaults to the local dev API. Override at build time with
// VITE_API_BASE=https://your-render-url.onrender.com for a deployed dashboard.
// Trailing slashes are stripped when building URLs (see http.ts), so either form works.
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

const request = makeRequest(API_BASE);

/** Non-null when a deployed page is still pointing at the localhost default (VITE_API_BASE not set at build). */
export function apiConfigHint(): string | null {
  const apiIsLocal = /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(API_BASE);
  const pageIsLocal = ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
  return apiIsLocal && !pageIsLocal
    ? `This dashboard is built to call ${API_BASE}, which is not reachable from here. Set VITE_API_BASE at build time.`
    : null;
}

export const api = {
  listRepos: (signal?: AbortSignal) => request<Repo[]>("/repos", { signal }),
  listRuns: async (repoId: number, signal?: AbortSignal) => {
    let total: number | null = null;
    const runs = await request<TestRunSummary[]>(`/repos/${repoId}/runs`, { signal }, (h) => {
      const n = Number(h.get("X-Total-Count"));
      total = h.has("X-Total-Count") && Number.isFinite(n) ? n : null;
    });
    return { runs, total: total ?? runs.length };
  },
  getFlakiness: (repoId: number, signal?: AbortSignal) =>
    request<FlakinessReport>(`/repos/${repoId}/flakiness`, { signal }),
  getImpactGraph: (repoId: number, signal?: AbortSignal) =>
    request<GraphSummary>(`/repos/${repoId}/impact/graph`, { signal }),
  analyzeImpact: (repoId: number, changedFiles: string[], signal?: AbortSignal) =>
    request<ImpactResponse>(`/repos/${repoId}/impact`, {
      method: "POST",
      signal,
      body: JSON.stringify({ changed_files: changedFiles }),
    }),
  getBenchmark: (signal?: AbortSignal) => request<BenchmarkResults>("/benchmark", { signal }),
};

export { ApiError };
