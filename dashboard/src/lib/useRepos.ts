import { useContext } from "react";
import { RepoContext } from "./RepoContext";

export function useRepos() {
  const ctx = useContext(RepoContext);
  if (!ctx) throw new Error("useRepos must be used within RepoProvider");
  return ctx;
}
