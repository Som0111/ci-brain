import { createContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { ApiError } from "./http";
import type { Repo } from "./types";

interface RepoContextValue {
  repos: Repo[];
  selectedRepoId: number | null;
  setSelectedRepoId: (id: number) => void;
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
  reload: () => void;
}

export const RepoContext = createContext<RepoContextValue | null>(null);

export function RepoProvider({ children }: { children: ReactNode }) {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    const cancelled = () => ctrl.signal.aborted;
    setLoading(true);
    setError(null);
    api
      .listRepos(ctrl.signal)
      .then((data) => {
        if (cancelled()) return;
        setRepos(data);
        // keep the current selection across a retry when that repo still exists
        setSelectedRepoId((cur) => (cur !== null && data.some((r) => r.id === cur) ? cur : (data[0]?.id ?? null)));
      })
      .catch((e) => {
        if (cancelled()) return;
        setError(e instanceof Error ? e.message : String(e));
        setErrorStatus(e instanceof ApiError ? e.status : null);
      })
      .finally(() => {
        if (!cancelled()) setLoading(false);
      });
    return () => ctrl.abort();
  }, [attempt]);

  return (
    <RepoContext.Provider
      value={{
        repos,
        selectedRepoId,
        setSelectedRepoId,
        loading,
        error,
        errorStatus,
        reload: () => setAttempt((a) => a + 1),
      }}
    >
      {children}
    </RepoContext.Provider>
  );
}
