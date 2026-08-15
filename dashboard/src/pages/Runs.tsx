import { api } from "../lib/api";
import { useApiData } from "../lib/useApiData";
import { useRepos } from "../lib/useRepos";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { StatusPill } from "../components/StatusPill";

export function Runs() {
  const { selectedRepoId } = useRepos();
  const { data: runs, loading, error } = useApiData(
    () => (selectedRepoId ? api.listRuns(selectedRepoId) : Promise.resolve([])),
    [selectedRepoId],
  );

  if (loading) return <LoadingState label="Loading runs" />;
  if (error) return <ErrorState message={error} />;
  if (!runs || runs.length === 0) return <EmptyState message="No runs recorded for this repo yet." />;

  return (
    <section>
      <h1>Run history</h1>
      <p className="page__subtitle">
        {runs.length} run{runs.length === 1 ? "" : "s"} ingested via the replay harness.
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Source</th>
              <th>Commit</th>
              <th>Branch</th>
              <th>Ingested</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td className="mono">#{run.id}</td>
                <td>
                  <StatusPill tone={run.source === "junit" ? "good" : "neutral"}>{run.source}</StatusPill>
                </td>
                <td className="mono">{run.commit_sha ? run.commit_sha.slice(0, 8) : "—"}</td>
                <td>{run.branch ?? "—"}</td>
                <td>{new Date(run.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
