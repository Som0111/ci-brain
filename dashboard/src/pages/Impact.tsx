import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { formatCount, formatPct } from "../lib/format";
import { useApiData } from "../lib/useApiData";
import { useRepos } from "../lib/useRepos";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { StatusPill } from "../components/StatusPill";
import type { ImpactResponse } from "../lib/types";

const EXAMPLE_FILES = ["toolz/dicttoolz.py", "toolz/itertoolz.py", "toolz/functoolz.py", "toolz/recipes.py"];

// Remounted per repo (see Impact below), so a typed query, result or error from the previous repo never lingers.
function ImpactBody() {
  const { selectedRepoId } = useRepos();
  const { data: graph, loading, error, errorStatus, reload } = useApiData(
    (signal) => (selectedRepoId ? api.getImpactGraph(selectedRepoId, signal) : Promise.resolve(null)),
    [selectedRepoId],
  );

  const [filesInput, setFilesInput] = useState(EXAMPLE_FILES[0]);
  const [result, setResult] = useState<ImpactResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef<AbortController | null>(null);
  useEffect(() => () => inFlight.current?.abort(), []);
  const [submitError, setSubmitError] = useState<{ message: string; status: number | null } | null>(null);

  async function runAnalysis(files: string) {
    if (!selectedRepoId) return;
    const changedFiles = files
      .split(/[\n,]/)
      .map((f) => f.trim())
      .filter(Boolean);
    if (changedFiles.length === 0) return;

    inFlight.current?.abort(); // a newer submit supersedes an older one
    const ctrl = new AbortController();
    inFlight.current = ctrl;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await api.analyzeImpact(selectedRepoId, changedFiles, ctrl.signal);
      if (!ctrl.signal.aborted) setResult(res);
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setSubmitError({
        message: e instanceof Error ? e.message : String(e),
        status: e instanceof ApiError ? e.status : null,
      });
    } finally {
      if (inFlight.current === ctrl) setSubmitting(false);
    }
  }

  if (loading) return <LoadingState label="Loading dependency graph" />;
  if (error) return <ErrorState message={error} status={errorStatus} onRetry={reload} />;

  return (
    <section>
      <h1>Test impact analysis</h1>
      <p className="page__subtitle">
        Coverage-graph dependency map, built from stored per-test coverage contexts. Enter changed
        file paths to see which tests would actually need to run.
      </p>

      {!graph || graph.files === 0 ? (
        <EmptyState message="No coverage data recorded for this repo yet — replay a run with coverage_json first." />
      ) : (
        <>
          <div className="stat-row">
            <div className="stat-tile">
              <span className="stat-tile__value">{graph.files}</span>
              <span className="stat-tile__label">Source files tracked</span>
            </div>
            <div className="stat-tile">
              <span className="stat-tile__value">{graph.edges}</span>
              <span className="stat-tile__label">File→test edges</span>
            </div>
          </div>

          <form
            className="impact-form"
            onSubmit={(e) => {
              e.preventDefault();
              runAnalysis(filesInput);
            }}
          >
            <label htmlFor="changed-files">Changed files (comma or newline separated)</label>
            <textarea
              id="changed-files"
              value={filesInput}
              onChange={(e) => setFilesInput(e.target.value)}
              rows={2}
            />
            <div className="impact-form__examples">
              Try:{" "}
              {EXAMPLE_FILES.map((f) => (
                <button type="button" key={f} className="chip" onClick={() => setFilesInput(f)}>
                  {f}
                </button>
              ))}
            </div>
            <button type="submit" disabled={submitting}>
              {submitting ? "Analyzing…" : "Analyze impact"}
            </button>
          </form>

          {submitError && <ErrorState message={submitError.message} status={submitError.status} />}

          {result && (
            <div className="impact-result">
              <div className="stat-row">
                <div className="stat-tile stat-tile--highlight">
                  <span className="stat-tile__value">
                    {formatCount(result.selected_count)}/{formatCount(result.total_tests)}
                  </span>
                  <span className="stat-tile__label">Tests selected</span>
                </div>
                <div className="stat-tile stat-tile--highlight">
                  <span className="stat-tile__value">{formatPct(result.reduction_pct)}</span>
                  <span className="stat-tile__label">Reduction</span>
                </div>
                <div className="stat-tile">
                  {result.full_suite_fallback ? (
                    <StatusPill tone="warning">Full-suite fallback</StatusPill>
                  ) : (
                    <StatusPill tone="good">Selective</StatusPill>
                  )}
                </div>
              </div>

              <h3>Why</h3>
              <ul className="reason-list">
                {result.reasons.map((r, i) => (
                  <li key={i} className="mono">
                    {r}
                  </li>
                ))}
              </ul>

              {result.selected_tests.length > 0 && (
                <>
                  <h3>Selected tests ({result.selected_tests.length})</h3>
                  <div className="test-list">
                    {result.selected_tests.map((t) => (
                      <div key={t} className="mono test-list__item">
                        {t}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function Impact() {
  const { selectedRepoId } = useRepos();
  return <ImpactBody key={selectedRepoId} />;
}
