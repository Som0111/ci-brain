export interface Repo {
  id: number;
  name: string;
  url: string | null;
  created_at: string;
}

export interface TestRunSummary {
  id: number;
  repo_id: number;
  commit_sha: string | null;
  branch: string | null;
  source: "junit" | "coverage";
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface FlakinessEntry {
  node_id: string;
  file_path: string;
  verdict: string;
  confidence: string | null;
  quarantine: boolean;
  pass_count: number;
  fail_count: number;
  skip_count: number;
  fail_rate: number;
}

export interface FlakinessReport {
  repo_id: number;
  commit_sha: string | null;
  total_tests: number;
  flaky: FlakinessEntry[];
  consistently_failing: FlakinessEntry[];
  insufficient_data: FlakinessEntry[];
  stable_count: number;
}

export interface GraphSummary {
  repo_id: number;
  files: number;
  edges: number;
  file_test_counts: Record<string, number>;
}

export interface ImpactResponse {
  repo_id: number;
  changed_files: string[];
  total_tests: number;
  selected_count: number;
  reduction_pct: number;
  full_suite_fallback: boolean;
  reasons: string[];
  unknown_files: string[];
  selected_tests: string[];
}

export interface BenchmarkScenario {
  changed_file: string;
  tests_selected: number;
  tests_total: number;
  test_count_reduction_pct: number;
  subset_median_s: number;
  runtime_reduction_pct: number;
  exec_time_reduction_pct: number;
}

export interface BenchmarkResults {
  variant: string;
  reps: number;
  full_suite_median_s: number;
  full_suite_overhead_s: number;
  full_suite_exec_s: number;
  scenarios: BenchmarkScenario[];
}
