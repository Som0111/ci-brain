# CI Brain

A CI test-intelligence platform for Python repos: it detects flaky tests statistically,
predicts the minimal set of tests to run for a code change (coverage-graph test impact
analysis, verified to never drop a real test failure), and clusters test failures by root
cause with an LLM-generated summary.

Built as a resume-shortlisting portfolio project targeting Core SDE / SWE internship roles.
Benchmarked against a real open-source repo ([`toolz`](https://github.com/pytoolz/toolz)) with
synthetic flaky tests and bugs deliberately seeded to exercise detection — clearly labeled as
synthetic throughout, never presented as organically discovered. See
[`docs/BENCHMARK.md`](docs/BENCHMARK.md) for full results and what's real vs. synthetic,
[`HUMAN_GUIDE.md`](HUMAN_GUIDE.md) for architecture and how to run it, and
[`docs/CI_Brain_Claude_Code_Roadmap.pdf`](docs/CI_Brain_Claude_Code_Roadmap.pdf) for the full
phase-by-phase build plan.

**Status: Phase 7 of 7 complete.** All 7 phases implemented, tested, and deployed. Benchmark
writeup and resume line ([`docs/BENCHMARK.md`](docs/BENCHMARK.md)) reviewed and approved.
<!-- TODO: link the live Render URL here once confirmed for public sharing -->

## What it does

- **Ingests** JUnit XML and coverage.py JSON (with per-test coverage contexts) from a target
  repo's CI runs.
- **Detects flaky tests**: flags a test as flaky when it produced both a pass and a fail on
  identical code — not a fail-rate threshold — with a confidence level and quarantine
  recommendation.
- **Predicts minimal test selection**: builds a file-to-test dependency graph from real
  coverage data, and for a set of changed files, selects only the tests that actually need to
  run — falling back to the full suite whenever it can't answer confidently (a config file
  changed, a source file has no coverage data, etc.).
- **Clusters failures by root cause** and generates a one-sentence plain-English hypothesis per
  cluster via a single LLM call (Google Gemini) — grounded in real evidence, never told the
  ground truth.
- **Dashboard** (React) over all of the above, plus a benchmark results view.

## Results (see [`docs/BENCHMARK.md`](docs/BENCHMARK.md) for full methodology)

- Test impact analysis: **9.5–58.2% wall-clock reduction, 57.5–98.9% fewer tests run** across
  four measured scenarios, with **zero missed test failures** verified empirically.
- Flaky-test detection: **4/4 seeded flaky tests correctly flagged, zero false positives**
  across 186 real tests.
- Failure clustering: 75 failures from 4 seeded bugs grouped into 12 clusters, with the two
  largest cleanly and exclusively isolating two of the bugs by root cause.

## Stack

FastAPI · PostgreSQL + SQLAlchemy + Alembic · pytest (98%+ branch coverage) · React + TypeScript
+ Vite · Google Gemini (failure summarization) · Docker + GitHub Actions CI/CD · deployed on
Render.

## Quickstart

```
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Or with Docker (Postgres + app, one command):

```
docker compose up --build
```

Dashboard (needs the API running above):

```
cd dashboard && npm install && npm run dev
```

See [`HUMAN_GUIDE.md`](HUMAN_GUIDE.md) for full setup, the replay harness, seeded benchmark
variants, deployment steps, and troubleshooting.

## Project layout

```
app/            FastAPI service: ingestion API, analysis (flakiness/impact/clustering/LLM)
scripts/        Replay harness, benchmark runner, safety verification, seed application
seeds/          Synthetic flaky tests + bugs, tracked in git (clearly labeled as synthetic)
dashboard/      React + TypeScript dashboard
docs/           Benchmark writeup, roadmap, project execution rules
tests/          110 tests, 98%+ branch coverage
```
