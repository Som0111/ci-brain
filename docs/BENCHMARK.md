# CI Brain — Benchmark & Results Writeup

**Status: approved.** Soumya reviewed and approved this writeup, the range framing
(9.5–58.2% wall-clock reduction), and the suggested resume line below — safe to quote publicly.

## What was measured, and against what

All numbers below come from replaying the real test suite of
[pytoolz/toolz](https://github.com/pytoolz/toolz) (a small, pure-Python utility library — 186
tests, ~2 seconds per run), pinned to commit `568c2b83` so every phase's numbers are
reproducible against the exact same code. Full methodology, including two real measurement
bugs found and fixed while producing these numbers, is in `DEVELOPER_GUIDE.md`.

## What's real and what's synthetic — read this before quoting anything

This is the section the roadmap explicitly requires, and it's the difference between an honest
resume line and a misleading one.

- **The target repo, its test suite, and its coverage data are real.** `toolz` is a real
  open-source project; its 186 tests are real tests; the coverage-graph dependency map in Phase
  4 is built from real execution data, not fabricated.
- **The flaky tests (Phase 3) are synthetic — deliberately seeded, not discovered.** Real repos
  don't reliably produce flaky tests on demand, so 4 synthetic flaky tests were written and
  added to a separate clone (`toolz-flaky-seed`), each tied to Python's per-process random seed
  so they're genuinely non-deterministic across runs. **These are not real bugs in `toolz`** —
  they were written for this project to have something to detect. The flakiness *detector*
  (the threshold logic, the statistical classification) is real, original work; the flaky
  *tests* it detected are synthetic test fixtures built for the purpose.
- **The bugs clustered in Phase 5 are synthetic — deliberately seeded, not discovered.** Same
  reasoning: 4 real, deterministic logic bugs (an off-by-one, a dropped `seen.add()` call, etc.)
  were intentionally written into a separate clone (`toolz-bug-seed`) to give the failure
  clustering and LLM summarization something to analyze. **`toolz` itself has no known bugs
  here** — these are injected regressions, clearly commented as such in the seed source
  (`seeds/bugs/*.py`), never presented as organically discovered defects.
- **The test-impact-analysis benchmark (Phase 4) numbers are real measurements**, not
  projections — see below.

## Test impact analysis — the numbers

Median of 9 interleaved reps, no coverage instrumentation (that's not part of a normal CI run
and would inflate the apparent saving), same checkout, quiet machine. Two independent
benchmark passes agreed to within 1.0 percentage point on every scenario.

| Changed file | Tests selected | Test-count reduction | Wall-clock reduction |
|---|---|---|---|
| `toolz/dicttoolz.py` | 52 / 186 | 72.0% | 42.4% |
| `toolz/itertoolz.py` | 58 / 186 | 68.8% | 9.5% |
| `toolz/functoolz.py` | 79 / 186 | 57.5% | 23.9% |
| `toolz/recipes.py` | 2 / 186 | 98.9% | 58.2% |

**Approved framing** (per Phase 4 sign-off): quote the *range* —
**9.5–58.2% wall-clock reduction, 57.5–98.9% fewer tests run, across four measured scenarios.**
Do not quote a single best-case number, and do not restate the test-count reduction as a
runtime saving — they measure different things, and on this suite ~47% of runtime is fixed
pytest startup overhead that no selection strategy can remove, so wall-clock reduction is
structurally smaller than test-count reduction.

## Flaky-test detection — the numbers

Detector correctly flagged **4/4 seeded flaky tests** (3 at high confidence, 1 at medium) with
**zero false positives** across the 186 real `toolz` tests, over 20 replayed runs.

## Failure clustering + LLM summarization — the numbers

75 failures (3 replayed runs × 25 failures/run, from the 4 seeded bugs) grouped into 12
clusters. The two largest clusters (18 and 6 failures) cleanly and exclusively isolated two of
the four seeded bugs by root cause. A documented, tested limitation: two bugs sharing one
source file (`itertoolz.py`) without a distinguishing signal in the failure text land in one
shared cluster rather than two — real fragmentation, not a false positive.

Two real LLM calls (Google Gemini) verified live: both produced accurate, specific root-cause
hypotheses (e.g. correctly identifying an off-by-one in `first()` from the failure text alone,
without being told which bug was seeded).

## Verification status and how to reproduce (added in the P2-14 audit)

Every public number, where it comes from, and what was re-checked. "Re-checked" means compared against the
checked-in artifacts without re-running the measurement; nothing here was re-measured.

| Claim | Source / command | Status |
|---|---|---|
| 186 tests, ~2 s full run, pinned commit `568c2b83` | `scripts/clone_target.py` (`TARGET_COMMIT`), `app/data/benchmark_results.json` | re-checked: 186 tests, full-suite median 2.12 s, commit matches script |
| Table above (4 scenarios, 9 reps) | `.venv\Scripts\python.exe -m scripts.benchmark_impact --reps 9`, artifact `app/data/benchmark_results.json` | re-checked: every row matches the committed artifact exactly |
| "Two passes agreed within 1.0 pp" | `replay_data/bench_A.json` vs `bench_B.json` (local, gitignored) | re-checked: max gap 1.0 pp (dicttoolz) |
| ~47% fixed pytest overhead | `full_suite_overhead_s / full_suite_median_s` | re-checked: 0.989 / 2.12 = 46.7% |
| "Never drops a real failure" | `python -m scripts.verify_selection` | **not re-run** (needs target clones + live DB). Covers `dicttoolz`, `itertoolz`, `functoolz`; a `recipes.py` scenario has now been added to the script but has **not been run** |
| Flaky detector 4/4, 0 false positives, 20 runs | `python -m scripts.replay_harness` + `GET /repos/{id}/flakiness` | not re-run (needs live DB); the 20 replay run directories exist locally |
| 75 failures -> 12 clusters; clusters of 18 and 6 | `GET /repos/{id}/failure-clusters` on the seeded repos | not re-run (needs live DB) |
| Two live Gemini hypotheses | `POST .../failure-clusters/summarize` | not reproducible on demand (external model, non-deterministic); recorded observation only |
| 98%+ coverage | `.venv\Scripts\python.exe -m pytest` | re-run in the P2 audit: ~98-99%, enforced floor is 90% |

**Accuracy flag on the resume line below:** it originally said the selection was verified never to drop a failure
"across all measured scenarios", but the failure-injection check was only ever defined for 3 of the 4 benchmarked
files (not `recipes.py`). The line has since been narrowed to "3 of 4 benchmarked scenarios".

**Scope of the safety claim:** it is an empirical result for single-file injected breakages in `toolz` at one pinned
commit, not a guarantee for arbitrary projects or multi-file changes.

**Environment:** the committed artifact predates environment capture, so the machine (CPU, OS, Python) that produced
the 2.12 s baseline was not recorded and cannot be reconstructed from the repo. `benchmark_impact.py` now writes an
`environment` block (UTC time, target commit, OS, CPU count, Python) on every new run; wall-clock figures are only
comparable across machines via the ratios, not the absolute seconds. Fixed pytest startup is ~1 s of the ~2.1 s
baseline, which is why wall-clock reduction is structurally smaller than test-count reduction.

## Resume line (approved)

> Built and deployed a CI test-intelligence platform (FastAPI, PostgreSQL, Docker, React) that
> reduces CI test suite runtime by 9.5–58.2% via coverage-graph-based test impact analysis
> (verified to never drop a real test failure across 3 of 4 benchmarked scenarios), with statistical
> flaky-test detection and LLM-assisted failure clustering; 98%+ test coverage, GitHub Actions
> CI/CD, deployed on Render.

Full re-run pending live environment with target repo clones.
