import { api } from "../lib/api";
import { formatCount, formatTimestamp } from "../lib/format";
import { useApiData } from "../lib/useApiData";
import { useRepos } from "../lib/useRepos";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { StatusPill } from "../components/StatusPill";

export function Runs() {
  const { selectedRepoId } = useRepos();
  const { data, loading, error, errorStatus, reload } = useApiData(
    (signal) => (selectedRepoId ? api.listRuns(selectedRepoId, signal) : Promise.resolve({ runs: [], total: 0 })),
    [selectedRepoId],
  );

  if (loading) return <LoadingState label="Loading runs" />;
  if (error) return <ErrorState message={error} status={errorStatus} onRetry={reload} />;
  if (!data || data.runs.length === 0) {
    return <EmptyState message="No runs have been ingested for this repo yet." />;
  }

  const { runs, total } = data;
  return (
    <section>
      <h1>Run history</h1>
      <p className="page__subtitle">
        {total > runs.length
          ? `Showing the newest ${formatCount(runs.length)} of ${formatCount(total)} runs.`
          : `${formatCount(total)} run${total === 1 ? "" : "s"} ingested via the replay harness.`}
      </p>

      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">Ingested test runs, newest first</caption>
          <thead>
            <tr>
              <th scope="col">Run</th>
              <th scope="col">Source</th>
              <th scope="col">Commit</th>
              <th scope="col">Branch</th>
              <th scope="col">Ingested</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td className="mono">#{run.id}</td>
                <td>
                  <StatusPill tone={run.source === "junit" ? "good" : "neutral"}>{run.source}</StatusPill>
                </td>
                <td className="mono" title={run.commit_sha ?? undefined}>
                  {run.commit_sha ? run.commit_sha.slice(0, 8) : "—"}
                </td>
                <td>{run.branch ?? "—"}</td>
                <td title={run.created_at}>{formatTimestamp(run.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
