import type {
  BenchmarkResults,
  FlakinessReport,
  GraphSummary,
  ImpactResponse,
  Repo,
  TestRunSummary,
} from "./types";

// Defaults to the local dev API. Override at build time with
// VITE_API_BASE=https://your-render-url.onrender.com for a deployed dashboard.
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText}: ${body}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  listRepos: () => request<Repo[]>("/repos"),
  listRuns: (repoId: number) => request<TestRunSummary[]>(`/repos/${repoId}/runs`),
  getFlakiness: (repoId: number) => request<FlakinessReport>(`/repos/${repoId}/flakiness`),
  getImpactGraph: (repoId: number) => request<GraphSummary>(`/repos/${repoId}/impact/graph`),
  analyzeImpact: (repoId: number, changedFiles: string[]) =>
    request<ImpactResponse>(`/repos/${repoId}/impact`, {
      method: "POST",
      body: JSON.stringify({ changed_files: changedFiles }),
    }),
  getBenchmark: () => request<BenchmarkResults>("/benchmark"),
};

export { ApiError };
