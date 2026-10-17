import { api } from "../lib/api";
import { formatCount, formatPercent } from "../lib/format";
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
      <td className="mono wrap" title={entry.node_id}>
        {entry.node_id}
      </td>
      <td>
        {entry.confidence && (
          <StatusPill tone={CONFIDENCE_TONE[entry.confidence] ?? "neutral"}>{entry.confidence}</StatusPill>
        )}
      </td>
      <td>{entry.quarantine ? <StatusPill tone="serious">quarantine</StatusPill> : "—"}</td>
      <td className="mono">
        {entry.pass_count}P / {entry.fail_count}F
      </td>
      <td className="mono">{formatPercent(entry.fail_rate)}</td>
    </tr>
  );
}

export function Flakiness() {
  const { selectedRepoId } = useRepos();
  const { data: report, loading, error, errorStatus, reload } = useApiData(
    (signal) => (selectedRepoId ? api.getFlakiness(selectedRepoId, signal) : Promise.resolve(null)),
    [selectedRepoId],
  );

  if (loading) return <LoadingState label="Loading flakiness report" />;
  if (error) return <ErrorState message={error} status={errorStatus} onRetry={reload} />;
  if (!report || report.total_tests === 0)
    return <EmptyState message="No test results have been ingested for this repo yet — replay some runs first." />;

  return (
    <section>
      <h1>Flaky tests</h1>
      <p className="page__subtitle">
        Flagged when a test produced both a pass and a fail across the analysed runs, not by a fail-rate
        threshold — see <span className="mono">app/analysis/classify.py</span> for the full rule.
        <em> Confidence</em> is an evidence label based on how often the rarer outcome was seen (3+ high,
        2 medium, 1 low); it is not a statistical probability.
      </p>

      {report.warning && (
        <div className="state state--warning" role="note">
          <strong>Results may mix code revisions.</strong>
          <div className="state__detail">{report.warning}</div>
        </div>
      )}

      <div className="stat-row">
        <div className="stat-tile">
          <span className="stat-tile__value">{formatCount(report.stable_count)}</span>
          <span className="stat-tile__label">Stable</span>
        </div>
        <div className="stat-tile stat-tile--flaky">
          <span className="stat-tile__value">{formatCount(report.flaky.length)}</span>
          <span className="stat-tile__label">Flaky</span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__value">{formatCount(report.consistently_failing.length)}</span>
          <span className="stat-tile__label">Consistently failing</span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__value">{formatCount(report.insufficient_data.length)}</span>
          <span className="stat-tile__label">Insufficient data</span>
        </div>
      </div>

      {report.flaky.length === 0 ? (
        <EmptyState message="No flaky tests detected in this repo's history." />
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Flaky tests, most observations first</caption>
            <thead>
              <tr>
                <th scope="col">Test</th>
                <th scope="col">Confidence</th>
                <th scope="col">Recommendation</th>
                <th scope="col">Pass / Fail</th>
                <th scope="col">Fail rate</th>
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
