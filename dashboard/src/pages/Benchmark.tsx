import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";
import { formatDuration, formatPct } from "../lib/format";
import { useApiData } from "../lib/useApiData";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import type { BenchmarkScenario } from "../lib/types";

function shortName(file: string): string {
  return file.split("/").pop() ?? file;
}

interface TooltipPayloadItem {
  name: string;
  value: number;
  color: string;
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipPayloadItem[]; label?: string }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__title">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="chart-tooltip__row">
          <span className="chart-tooltip__swatch" style={{ background: p.color }} />
          <span>{p.name}</span>
          <span className="chart-tooltip__value">{p.value.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}

export function Benchmark() {
  const { data: results, loading, error, errorStatus, reload } = useApiData((signal) => api.getBenchmark(signal), []);

  if (loading) return <LoadingState label="Loading benchmark results" />;
  if (error) return <ErrorState message={error} status={errorStatus} onRetry={reload} />;
  if (!results || results.scenarios.length === 0) {
    return <EmptyState message="No benchmark results are recorded on the server." />;
  }

  const chartData = results.scenarios.map((s: BenchmarkScenario) => ({
    scenario: shortName(s.changed_file),
    "Test-count cut": s.test_count_reduction_pct,
    "Wall-clock cut": s.runtime_reduction_pct,
    "Execution-time cut": s.exec_time_reduction_pct,
  }));

  return (
    <section>
      <h1>Test impact analysis benchmark</h1>
      <p className="page__subtitle">
        Median of {results.reps} interleaved reps against a real repo ({results.variant}), no
        coverage instrumentation. This is a recorded snapshot from Phase 4, not recomputed on
        every page load — see DEVELOPER_GUIDE.md for the full methodology, including two measurement
        bugs found and fixed while producing these numbers.
      </p>

      <div className="stat-row">
        <div className="stat-tile">
          <span className="stat-tile__value">{formatDuration(results.full_suite_median_s)}</span>
          <span className="stat-tile__label">Full suite runtime</span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__value">
            {((results.full_suite_overhead_s / results.full_suite_median_s) * 100).toFixed(0)}%
          </span>
          <span className="stat-tile__label">Fixed pytest overhead</span>
        </div>
      </div>

      <div
        className="viz-root chart-card"
        role="img"
        aria-label={`Grouped bar chart of test-count, wall-clock and execution-time reduction for ${results.scenarios.length} changed-file scenarios. The same values are in the table below.`}
      >
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }} barGap={2} barCategoryGap="20%">
            <CartesianGrid vertical={false} stroke="var(--gridline)" />
            <XAxis dataKey="scenario" tick={{ fill: "var(--text-muted)", fontSize: 13 }} axisLine={{ stroke: "var(--axis)" }} tickLine={false} />
            <YAxis
              tick={{ fill: "var(--text-muted)", fontSize: 13 }}
              axisLine={false}
              tickLine={false}
              unit="%"
              domain={[0, 100]}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--hover-wash)" }} />
            <Legend wrapperStyle={{ fontSize: 13, color: "var(--text-secondary)" }} />
            <Bar dataKey="Test-count cut" fill="var(--series-1)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="Wall-clock cut" fill="var(--series-2)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="Execution-time cut" fill="var(--series-3)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <h3>Table view</h3>
      <p className="text-muted" style={{ marginTop: "-0.5rem", marginBottom: "0.75rem" }}>
        Test-count and wall-clock reduction are not interchangeable: tests aren't uniform in
        duration, so cutting most tests doesn't cut most runtime.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Changed file</th>
              <th scope="col">Tests selected</th>
              <th scope="col">Test-count cut</th>
              <th scope="col">Wall-clock cut</th>
              <th scope="col">Execution-time cut</th>
            </tr>
          </thead>
          <tbody>
            {results.scenarios.map((s) => (
              <tr key={s.changed_file}>
                <td className="mono">{s.changed_file}</td>
                <td className="mono">
                  {s.tests_selected}/{s.tests_total}
                </td>
                <td className="mono">{formatPct(s.test_count_reduction_pct)}</td>
                <td className="mono">{formatPct(s.runtime_reduction_pct)}</td>
                <td className="mono">{formatPct(s.exec_time_reduction_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
