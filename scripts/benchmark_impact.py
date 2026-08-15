"""Benchmark: full-suite runtime vs impact-selected-subset runtime.

Methodology notes that materially affect the resulting number - read these
before quoting it anywhere:

- **No coverage instrumentation.** Coverage roughly doubles runtime and is not
  part of a normal CI test run, so benchmarking with it on would inflate the
  apparent saving. Both arms run plain pytest.
- **Same machine, same checkout, sequential.** Both arms run back-to-back in
  the same environment against the identical working tree, so the only
  variable is which tests were selected.
- **Median of N repetitions**, after a discarded warm-up run (first run pays
  import/bytecode-cache costs the others don't).
- **Arms are interleaved (A/B/A/B), not measured in blocks.** Measuring every
  full-suite rep and then every subset rep lets machine drift (thermal state,
  background processes) land entirely on one arm. A first attempt at this
  benchmark did exactly that and the reduction figure for one scenario moved
  24 percentage points between two runs. Round-robin sampling puts drift on
  both arms equally. It does not bias the result in either direction - it
  narrows the spread.
- **Fixed overhead is measured per arm** via `--collect-only` on that arm's
  exact argument list. A global "floor" measured over the whole directory is
  *not* valid here: passing explicit node ids makes pytest collect only the
  files involved, so a narrow selection has a genuinely smaller fixed cost.
  Using the global floor produced a nonsensical ">100% of reducible time
  captured" for a 2-test selection, which is what prompted this decomposition.
- **Wall-clock and test-count reductions are reported separately and are not
  interchangeable.** Tests are not uniform in duration, so cutting 70% of
  tests does not cut 70% of runtime - it can be far less if the selected
  tests happen to be the slow ones. The execution-time column below strips
  fixed overhead out to show what selection actually saved in test work.
"""
import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path

from app.analysis.impact import (
    build_dependency_graph,
    get_all_tests,
    get_tests_by_file,
    select_tests,
    to_pytest_nodeid,
)
from app.database import SessionLocal
from app.models import TestCase
from scripts.clone_target import target_dir
from scripts.run_target_tests import target_python
from sqlalchemy import select as sa_select

SCENARIOS = ["toolz/dicttoolz.py", "toolz/itertoolz.py", "toolz/functoolz.py", "toolz/recipes.py"]


def time_pytest(variant: str, args: list[str]) -> float:
    py = target_python(variant)
    start = time.perf_counter()
    subprocess.run(
        [str(py), "-m", "pytest", *args, "-q", "-p", "no:cacheprovider"],
        cwd=target_dir(variant),
        capture_output=True,
    )
    return time.perf_counter() - start


def measure_interleaved(variant: str, arms: dict[str, list[str]], reps: int) -> dict[str, dict]:
    """Time every arm once per round, round-robin, so machine drift over the
    course of the benchmark lands on all arms equally rather than on whichever
    one happened to be measured last."""
    samples: dict[str, list[float]] = {name: [] for name in arms}
    for rep in range(reps):
        print(f"  round {rep + 1}/{reps}...")
        for name, argv in arms.items():
            samples[name].append(time_pytest(variant, argv))
    return {
        name: {
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
            "runs": [round(t, 3) for t in times],
        }
        for name, times in samples.items()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="toolz")
    parser.add_argument("--repo-id", type=int, default=1)
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--out", default="replay_data/benchmark.json")
    args = parser.parse_args()

    db = SessionLocal()
    graph = build_dependency_graph(db, args.repo_id)
    all_tests = get_all_tests(db, args.repo_id)
    tests_by_file = get_tests_by_file(db, args.repo_id)
    path_by_node = {
        tc.node_id: tc.file_path
        for tc in db.scalars(sa_select(TestCase).where(TestCase.repo_id == args.repo_id)).all()
    }
    db.close()

    print("warm-up run (discarded)...")
    time_pytest(args.variant, ["toolz/"])

    selections = {}
    arms: dict[str, list[str]] = {
        "full": ["toolz/"],
        "full_collect": ["toolz/", "--collect-only"],
    }
    for source_file in SCENARIOS:
        selection = select_tests([source_file], graph, all_tests, tests_by_file)
        nodeids = [to_pytest_nodeid(n, path_by_node[n]) for n in sorted(selection.selected)]
        selections[source_file] = nodeids
        arms[f"subset::{source_file}"] = nodeids
        arms[f"collect::{source_file}"] = [*nodeids, "--collect-only"]

    print(f"measuring {len(arms)} arms, interleaved, {args.reps} rounds...")
    m = measure_interleaved(args.variant, arms, args.reps)

    full = m["full"]
    full_overhead = m["full_collect"]
    full_exec = full["median"] - full_overhead["median"]

    results = []
    for source_file in SCENARIOS:
        nodeids = selections[source_file]
        subset = m[f"subset::{source_file}"]
        subset_overhead = m[f"collect::{source_file}"]
        subset_exec = max(subset["median"] - subset_overhead["median"], 0.0)

        test_reduction = (1 - len(nodeids) / len(all_tests)) * 100
        runtime_reduction = (1 - subset["median"] / full["median"]) * 100
        exec_reduction = (1 - subset_exec / full_exec) * 100 if full_exec > 0 else 0.0

        results.append({
            "changed_file": source_file,
            "tests_selected": len(nodeids),
            "tests_total": len(all_tests),
            "test_count_reduction_pct": round(test_reduction, 1),
            "subset_median_s": round(subset["median"], 3),
            "subset_stdev_s": round(subset["stdev"], 3),
            "subset_overhead_s": round(subset_overhead["median"], 3),
            "subset_exec_s": round(subset_exec, 3),
            "runtime_reduction_pct": round(runtime_reduction, 1),
            "exec_time_reduction_pct": round(exec_reduction, 1),
            "subset_runs": subset["runs"],
        })

    report = {
        "variant": args.variant,
        "reps": args.reps,
        "full_suite_median_s": round(full["median"], 3),
        "full_suite_min_s": round(full["min"], 3),
        "full_suite_max_s": round(full["max"], 3),
        "full_suite_stdev_s": round(full["stdev"], 3),
        "full_suite_runs": full["runs"],
        "full_suite_overhead_s": round(full_overhead["median"], 3),
        "full_suite_exec_s": round(full_exec, 3),
        "scenarios": results,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nfull suite: {report['full_suite_median_s']}s "
          f"(range {report['full_suite_min_s']}-{report['full_suite_max_s']}s)")
    print(f"  of which fixed startup+collection: {report['full_suite_overhead_s']}s "
          f"({report['full_suite_overhead_s'] / report['full_suite_median_s'] * 100:.0f}%), "
          f"actual test execution: {report['full_suite_exec_s']}s")
    print(f"\n{'changed file':<24}{'tests':>12}{'test cut':>10}{'wall':>8}{'wall cut':>10}{'exec cut':>10}")
    for r in results:
        print(f"{r['changed_file']:<24}{r['tests_selected']:>5}/{r['tests_total']:<6}"
              f"{r['test_count_reduction_pct']:>9.1f}%{r['subset_median_s']:>7.2f}s"
              f"{r['runtime_reduction_pct']:>9.1f}%{r['exec_time_reduction_pct']:>9.1f}%")
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
