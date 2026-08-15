import { api } from "../lib/api";
import { useApiData } from "../lib/useApiData";
import { useRepos } from "../lib/useRepos";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { StatusPill } from "../components/StatusPill";
import type { FlakinessEntry } from "../lib/types";

const CONFIDENCE_TONE: Record<string, "critical" | "warning" | "neutral"> = {
  high: "critical",
  medium: "warning",
  low: "neutral",
};

function FlakyRow({ entry }: { entry: FlakinessEntry }) {
  return (
    <tr>
      <td className="mono">{entry.node_id}</td>
      <td>
        {entry.confidence && (
          <StatusPill tone={CONFIDENCE_TONE[entry.confidence] ?? "neutral"}>{entry.confidence}</StatusPill>
        )}
      </td>
      <td>{entry.quarantine ? <StatusPill tone="serious">quarantine</StatusPill> : "—"}</td>
      <td className="mono">
        {entry.pass_count}P / {entry.fail_count}F
      </td>
      <td className="mono">{(entry.fail_rate * 100).toFixed(0)}%</td>
    </tr>
  );
}

export function Flakiness() {
  const { selectedRepoId } = useRepos();
  const { data: report, loading, error } = useApiData(
    () => (selectedRepoId ? api.getFlakiness(selectedRepoId) : Promise.resolve(null)),
    [selectedRepoId],
  );

  if (loading) return <LoadingState label="Loading flakiness report" />;
  if (error) return <ErrorState message={error} />;
  if (!report || report.total_tests === 0)
    return <EmptyState message="No test history for this repo yet — replay some runs first." />;

  return (
    <section>
      <h1>Flaky tests</h1>
      <p className="page__subtitle">
        Flagged when a test produced both a pass and a fail on identical code, not by a fail-rate
        threshold — see <span className="mono">app/analysis/classify.py</span> for the full rule.
      </p>

      <div className="stat-row">
        <div className="stat-tile">
          <span className="stat-tile__value">{report.stable_count}</span>
          <span className="stat-tile__label">Stable</span>
        </div>
        <div className="stat-tile stat-tile--flaky">
          <span className="stat-tile__value">{report.flaky.length}</span>
          <span className="stat-tile__label">Flaky</span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__value">{report.consistently_failing.length}</span>
          <span className="stat-tile__label">Consistently failing</span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__value">{report.insufficient_data.length}</span>
          <span className="stat-tile__label">Insufficient data</span>
        </div>
      </div>

      {report.flaky.length === 0 ? (
        <EmptyState message="No flaky tests detected in this repo's history." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Test</th>
                <th>Confidence</th>
                <th>Recommendation</th>
                <th>Pass / Fail</th>
                <th>Fail rate</th>
              </tr>
            </thead>
            <tbody>
              {report.flaky
                .slice()
                .sort((a, b) => b.fail_count + b.pass_count - (a.fail_count + a.pass_count))
                .map((entry) => (
                  <FlakyRow key={entry.node_id} entry={entry} />
                ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
