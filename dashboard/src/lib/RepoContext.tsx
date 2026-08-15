import { createContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Repo } from "./types";

interface RepoContextValue {
  repos: Repo[];
  selectedRepoId: number | null;
  setSelectedRepoId: (id: number) => void;
  loading: boolean;
  error: string | null;
}

export const RepoContext = createContext<RepoContextValue | null>(null);

export function RepoProvider({ children }: { children: ReactNode }) {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listRepos()
      .then((data) => {
        setRepos(data);
        if (data.length > 0) setSelectedRepoId(data[0].id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <RepoContext.Provider value={{ repos, selectedRepoId, setSelectedRepoId, loading, error }}>
      {children}
    </RepoContext.Provider>
  );
}
