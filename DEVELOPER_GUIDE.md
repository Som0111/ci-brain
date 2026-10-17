# CI Brain — Developer Guide

Single reference doc for this project. Updated at the end of every completed phase.

## What this project does

A CI test-intelligence platform for Python repos. It ingests test-run data (JUnit XML,
coverage.py JSON with per-test contexts) from a target repo's CI, and:

- **Detects flaky tests statistically** — flags tests that produced both a pass and a fail on
  identical code, with a confidence level and a quarantine recommendation (Phase 3).
- **Predicts the minimal test subset for a code change**, via a coverage-graph dependency map
  built from real execution data, with conservative full-suite fallbacks whenever the graph
  can't answer confidently (Phase 4).
- **Clusters test failures by likely root cause** and generates a plain-English hypothesis per
  cluster via a single LLM call (Google Gemini) (Phase 5).
- Ships as a Dockerized, CI/CD'd FastAPI service (deployed on Render) with a React dashboard
  over all of the above (Phases 6-7).

Benchmarked against a real open-source Python repo (`toolz`), with synthetic flaky tests and
synthetic bugs deliberately seeded into separate clones to exercise detection and clustering —
clearly labeled as synthetic throughout, never presented as organically discovered. See
`docs/CI_Brain_Roadmap.pdf` for the full phase plan and locked scope decisions.

## Why the major components exist

- **FastAPI app** (`app/`) — the ingestion/query/analysis API everything else is built on.
  Routers in `app/api/`: `repos`, `runs` (ingestion), `flakiness`, `impact`, `clusters`
  (+ LLM summarize), `benchmark`.
- **SQLAlchemy models** (`app/models.py`) — `Repo`, `TestCase`, `TestRun`, `TestResult`. Kept
  minimal and normalized from Phase 1 since every later phase reads from and writes to it.
- **Analysis layer** (`app/analysis/`) — pure logic, no FastAPI dependency, independently
  testable: `flakiness.py` (variance computation), `classify.py` (flaky/stable/failing
  verdicts), `impact.py` (dependency graph + test selection), `clustering.py` (failure
  grouping), `summarize.py` (the one LLM call).
- **Parsers** (`app/parsers/`) — JUnit XML and coverage.py JSON, pure functions.
- **Alembic** (`alembic/`) — schema migrations, hand-written for the initial migration since
  there was no live database to diff against when it was written.
- **Replay harness** (`scripts/`) — clones the benchmark target repo (`toolz`, and seeded
  variants of it), runs the real test suite with coverage, pushes each run through the
  ingestion API. This generates all the real data every analysis phase operates on. Also:
  `verify_selection.py` (empirically checks impact analysis never drops a real failure, verified across 3 of 4
  benchmarked scenarios; full re-run pending live environment with target repo clones),
  `benchmark_impact.py` (the Phase 4 runtime benchmark), `apply_seed.py` (applies tracked seed
  files from `seeds/` onto a disposable clone).
- **Dashboard** (`dashboard/`) — React + TypeScript + Vite, four views over the real API (run
  history, flaky tests, impact analysis, benchmark chart). See `dashboard/README.md`.
- **Docker** (`Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`) and **CI/CD**
  (`.github/workflows/`) — see the Phase 6 log entry below for what each piece does and why.

## Architecture / design decisions worth knowing

- `TestCase` rows are deduplicated per repo by `(repo_id, node_id)` — re-ingesting the same
  test across multiple runs reuses the same `TestCase` row and just adds new `TestResult`
  rows. This is what makes cross-run analysis (flakiness, impact analysis) possible.
- `TestRun.coverage_data` stores the raw `coverage json` output as-is (a JSON column).
  `app/analysis/impact.py` is what turns accumulated coverage data across runs into the
  file-to-test dependency graph.
- Enum columns (`TestRun.source`, `TestResult.status`) use `values_callable` so SQLAlchemy
  writes the enum's lowercase `.value` ("junit", "passed") to Postgres, not the uppercase
  Python member name. **This bit us once** — see Known limitations / gotchas.
- Local test suite (`tests/`) runs against an in-memory SQLite DB, not Postgres, so it has zero
  external dependencies and runs in ~2.5s. 110 tests, 98%+ branch coverage, enforced via
  `--cov-fail-under=90` in `pytest.ini`.
- **Benchmark target repo is `toolz`** ([pytoolz/toolz](https://github.com/pytoolz/toolz)),
  pinned to commit `568c2b8393973cd172a466546c9d95779c452438`. Picked because it's pure Python
  with zero dependencies (fast, no install/env risk), has no I/O or real concurrency (tests are
  deterministic by default — flakiness only shows up when *we* seed it), and its source is
  cleanly split into separate modules each with their own test file — which gives the
  file-to-test dependency graph real structure instead of every test touching every file.
  186 tests, ~2-3s per full run.
- Coverage is collected with **per-test contexts** (`--cov-context=test`, then
  `coverage json --show-contexts`), not plain aggregate coverage. This records *which specific
  test* executed each line, which is what makes a real file-to-test map possible.

## How to run it locally

1. Postgres must be running with a `ci_brain` database and user (native PostgreSQL 18 install,
   or `docker compose up --build` handles this automatically — see below).
2. From `C:\Users\USER\projects\ci-brain`:
   ```
   .venv\Scripts\python.exe -m alembic upgrade head      # apply migrations (once, or after new ones are added)
   .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
   ```
3. API is at `http://127.0.0.1:8000`. `/health` should return `{"status":"ok"}`.
4. Dashboard (optional, separate terminal):
   ```
   cd dashboard
   npm install
   npm run dev
   ```
   Opens at `http://localhost:5173`, pointing at the API above by default.

## How to run the replay harness (against `toolz`)

With the API already running (step above):

```
.venv\Scripts\python.exe scripts\clone_target.py          # one-time: clones toolz + sets up its own isolated venv
.venv\Scripts\python.exe -m scripts.replay_harness -n 5    # runs the suite 5x, pushes each run to the API
```

`clone_target.py` is idempotent — safe to re-run any time, it'll just check out the pinned
commit again and reuse the existing venv. Artifacts land in `replay_data/run_N/` (gitignored).
Spot-check: `curl http://localhost:8000/runs/<id>` and compare `results` count / status
breakdown against the raw `replay_data/run_N/junit.xml`.

## How to set up a seeded variant (flaky tests, synthetic bugs)

Seed source files live in `seeds/` (tracked in git) — the clone under `target_repos/` is
gitignored and disposable, so seeding is a separate explicit step, not a hand-edit in the clone:

```
.venv\Scripts\python.exe scripts\clone_target.py --variant toolz-flaky-seed
.venv\Scripts\python.exe -m scripts.apply_seed --variant toolz-flaky-seed --seed-file flaky/test_seeded_flaky.py --dest toolz/tests/test_seeded_flaky.py
.venv\Scripts\python.exe -m scripts.replay_harness -n 20 --variant toolz-flaky-seed --repo-name toolz-flaky-seed --out-prefix flaky_run
```

Same pattern for the bug-seeded variant (`toolz-bug-seed`, 4 seed files under `seeds/bugs/`).

## How to run the impact analysis + benchmark (Phase 4)

```
.venv\Scripts\python.exe -m scripts.verify_selection      # safety check: does selection ever drop a real failure?
.venv\Scripts\python.exe -m scripts.benchmark_impact --reps 9   # the published numbers used 9 reps
```

`verify_selection.py` is the one that matters for trusting any number: it breaks a source file,
runs the **full** suite, and asserts every test that actually failed was in the selected
subset. It restores the file afterwards (both by rewriting the original text and `git
checkout`). Real Phase 4 results are committed at `app/data/benchmark_results.json` and served
via `GET /benchmark` — see the Phase 4 log entry for full methodology and numbers.

## How to run it with Docker (local)

**Verified working end-to-end**: `db-1` reaches healthy, the app container's entrypoint runs
the Alembic migration, Uvicorn serves on `:8000`.

1. From `C:\Users\USER\projects\ci-brain`:
   ```
   docker compose up --build
   ```
2. First run pulls the Postgres image and builds the app image — takes a few minutes. Once
   both containers are up, API is at `http://localhost:8000/health`.
3. `docker compose down` to stop; add `-v` to also delete the Postgres volume (fresh DB next
   time, re-runs migrations from scratch).

## How to deploy (Render) — one-time manual steps

Docker + GitHub Actions handle build validation automatically; the actual deploy is Render's
own GitHub integration (auto-deploys on every push to `master`), connected once by hand —
Render account/secrets aren't something anyone but Soumya can set up.

**Part 1 — create the Postgres database:**
1. Go to `dashboard.render.com`, log in (same account as ChurnGuard).
2. Click **New +** (top right) → **PostgreSQL**.
3. Name it `ci-brain-db`, leave the rest default, click **Create Database**.
4. Once provisioned, find **Internal Database URL** on the database's page and copy it (looks
   like `postgresql://ci_brain_db_user:...@dpg-xxxx/ci_brain_db`) — you'll paste this in Part 2.

**Part 2 — create the web service:**
1. Click **New +** → **Web Service**.
2. **Build and deploy from a Git repository** → select `Som0111/ci-brain` → **Connect**.
3. **Name**: `ci-brain`. **Branch**: `master`. **Runtime**: **Docker** (Render detects the
   `Dockerfile` automatically).
4. **Environment Variables**: add `DATABASE_URL` (the Internal Database URL from Part 1, pasted
   as-is — no need to change `postgresql://` to `postgresql+psycopg2://`) and `GEMINI_API_KEY`
   (same value as local `.env`).
5. **Free** instance type → **Create Web Service**. Watch the **Logs** tab; the entrypoint runs
   `alembic upgrade head` before starting the server, so migration errors show up there first.
6. Once live, test `/health` on the Render URL — expect `{"status":"ok"}`. Free tier sleeps
   after 15 min idle; first request after that takes ~50s (same as ChurnGuard).

After this one-time setup, every push to `master` auto-triggers a new build and deploy.

**Confirmed live**: https://ci-brain.onrender.com/health returns `{"status":"ok"}`.

## How to test it

```
.venv\Scripts\python.exe -m pytest -q
```
No Postgres needed — tests use in-memory SQLite (see `tests/conftest.py`). Runs with coverage
by default and fails if branch coverage drops below 90% (`pytest.ini` / `.coveragerc`).

Dashboard: `cd dashboard && npm run lint && npx tsc -b --noEmit && npm run build`.

## Important commands

| What | Command |
|---|---|
| Install deps | `.venv\Scripts\python.exe -m pip install -r requirements.txt` |
| Run tests (with coverage) | `.venv\Scripts\python.exe -m pytest -q` |
| Lint | `.venv\Scripts\python.exe -m ruff check app/ tests/ scripts/` |
| Apply migrations | `.venv\Scripts\python.exe -m alembic upgrade head` |
| Run the API | `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload` |
| Set up/refresh target repo | `.venv\Scripts\python.exe scripts\clone_target.py --variant <name>` |
| Apply a seed onto a variant | `.venv\Scripts\python.exe -m scripts.apply_seed --variant <name> --seed-file <path> --dest <path>` |
| Replay N runs into the API | `.venv\Scripts\python.exe -m scripts.replay_harness -n 5 --variant <name> --repo-name <name>` |
| Verify impact selection is safe | `.venv\Scripts\python.exe -m scripts.verify_selection` |
| Run the benchmark | `.venv\Scripts\python.exe -m scripts.benchmark_impact --reps 9` |
| Run everything in Docker | `docker compose up --build` |
| Run the dashboard | `cd dashboard && npm run dev` |

## Known limitations / gotchas

- **Database export tooling, and an unresolved Render free-tier flakiness pattern.**
  `scripts/export_db.py` connects directly to Postgres (complete, includes `coverage_data`,
  needs a DB URL with external network access) and `scripts/export_db_via_api.py` walks the
  public API instead (no DB credentials needed, but never includes `coverage_data` - the API
  doesn't expose it). A direct-DB export attempt against the live Render Postgres timed out at
  the raw TCP level on port 5432 even with Render's Access Control set to `0.0.0.0/0` - `Test-
  NetConnection` confirmed port 443 and DNS (53) work fine from the same machine, only 5432
  doesn't, which points at a local/ISP network block on that specific port, not a Render-side
  restriction. Falling back to the API export, `GET /repos/{id}/runs` (and then even individual
  `GET /runs/{id}` lookups) started 502ing specifically for the repo with 20 runs while the
  same request for the 5-run repo kept working - **reproduced as fine locally against the
  identical data**, so this is a live-environment issue (most likely free-tier RAM/CPU limits
  under sustained query load compounding with each retry), not an application bug. The
  resulting export (`exports/ci_brain_render_export_*.json`) is honestly marked partial in its
  own `warnings` field rather than silently missing data. Re-running the API export once the
  deploy has had a quiet period should pick up the rest; if it keeps failing specifically on
  larger responses, that's worth checking against Render's actual service logs/metrics (not
  visible from here) before assuming it's fixed by more code changes.
- **The Render deploy 502'd on every DB-touching endpoint after a sustained ingestion burst**
  (25 replay-harness requests back to back), while `/health` (no DB) kept returning 200 the
  whole time — a clean signature of a dead pooled connection, not the app itself being down.
  `create_engine()` had no `pool_pre_ping`, so SQLAlchemy kept handing out a connection that
  Render's free-tier Postgres had already dropped (idle timeout or a restart under load)
  instead of detecting and replacing it. Fixed with `pool_pre_ping=True` (validates before
  each checkout) and `pool_recycle=280` (proactively recycles before a server-side idle limit
  hits) in `app/database.py`. If this recurs after a quiet period rather than under load,
  that's the same root cause from a different trigger.
- No auth on any endpoint — fine for a local/portfolio project, not fine for anything public.
  CORS is wide open (`allow_origins=["*"]`) for the same reason (see `app/main.py`).
- Ingestion identifies a run only by `repo_id` path param; there's no idempotency/dedup if the
  same JUnit file is POSTed twice (creates a second `TestRun`).
- **SQLite vs Postgres divergence bit us once**: the enum `values_callable` bug only showed up
  against real Postgres — SQLite has no native enum type, so it silently accepted whatever
  string SQLAlchemy sent. If something works in `pytest` but fails against the real API,
  suspect a SQLite/Postgres behavioral difference first.
- **coverage.py's default tracer breaks per-test contexts on Python 3.12+**: coverage.py 7.x
  defaults to the new `sysmon` core, which doesn't fully support dynamic contexts and raises
  `CoverageWarning: Dynamic contexts aren't supported with core=sysmon` — which `toolz`'s
  `filterwarnings=error` config turns into a hard test failure. Fixed via `COVERAGE_CORE=ctrace`
  in `scripts/run_target_tests.py`. If a *different* target repo is ever swapped in and
  contexts silently come back empty, check this first.
- **Postgres 18+'s official image changed its expected volume mount point**: wants the named
  volume at the parent `/var/lib/postgresql`, not `/var/lib/postgresql/data` as most older
  Compose examples use — it manages a version-specific subdirectory itself now, for
  `pg_upgrade` compatibility. Fixed in `docker-compose.yml`; see
  https://github.com/docker-library/postgres/pull/1259.
- **Seeded-flaky variance is real but skewed, not 50/50**: the 4 synthetic flaky tests in
  `seeds/flaky/test_seeded_flaky.py` have empirical fail rates from 40% to 90% (measured across
  20 runs) — real flaky tests usually aren't 50/50 either. One test only has a ~1-in-6 chance to
  pass by construction, so it needs a reasonably large N to show both outcomes.
- **Failure clustering can't separate two bugs sharing one file without a "where" hint**: see
  the Phase 5 log entry. A real, tested, documented heuristic limitation, not a bug.
- **Two lint rules disabled, both with a documented reason, not silenced arbitrarily**:
  Python's ruff `B008` (flags FastAPI's `Depends()` pattern as a bug) and the dashboard's oxlint
  `react-hooks/exhaustive-deps` + `react/only-export-components` (both fire on legitimate
  small-project patterns here). See the relevant phase log entries.

## What changed in each completed phase

### Phase 1 — Scaffold + Ingestion API
- FastAPI skeleton, SQLAlchemy models, Alembic migrations, `POST /repos`,
  `POST /repos/{id}/runs` (JUnit XML and/or coverage.py JSON), `GET /repos`,
  `GET /repos/{id}/runs`, `GET /repos/{id}/tests`, `GET /runs/{id}`.
- 20 unit/integration tests (parser edge cases + malformed input + API round-trip).
- Verified end-to-end against a real local Postgres 18 instance, not just the SQLite test
  suite. This is where the enum bug above was caught and fixed.

### Phase 2 — Replay Harness
- Target repo picked and validated: `toolz`, pinned to `568c2b83`, 186 tests, ~2-3s full run.
- `scripts/clone_target.py` (idempotent clone + isolated venv), `scripts/run_target_tests.py`
  (runs the suite once with per-test coverage contexts), `scripts/coverage_map.py` (one run's
  coverage JSON → file-to-test map), `scripts/replay_harness.py` (loops N runs into the API).
- Verified: 3 replay cycles against the live API, stored result counts and status breakdowns
  matched raw `junit.xml` exactly, `commit_sha` matched the pinned target commit.

### Phase 3 — Flakiness Detection
- Seeded 4 synthetic flaky tests (`seeds/flaky/test_seeded_flaky.py`) into a separate clone
  (`toolz-flaky-seed`), each tied to `random`'s per-process seed rather than raw OS timing
  jitter, so they're reliably non-deterministic across independent `pytest` process runs.
- `app/analysis/flakiness.py` (`compute_variance_stats`) tallies pass/fail/skip counts per test
  across stored runs.
- **Threshold decision** (`app/analysis/classify.py`, reviewed on Fable per the model usage
  guide, approved): a test is **flaky** if it produced both a pass and a fail on identical code
  — not a fail-rate percentage band, because a 5% fail rate is still flaky while a 100% fail
  rate is just a broken test (reported separately as "consistently failing"). **Confidence**
  comes from the minority-outcome count: seen 3+ times = high, 2 = medium, 1 = low.
  **Quarantine** recommended at medium+ confidence. Fewer than 5 non-skip runs = "insufficient
  data" — refuse to classify rather than guess.
- Report endpoint: `GET /repos/{id}/flakiness` (optional `?commit_sha=`).
- Verified live against 20 seeded runs: 4/4 seeded flaky tests flagged (3 high, 1 medium
  confidence, all quarantined), 186/186 real tests stable, zero false positives.

### Phase 4 — Test Impact Analysis

> Benchmark framing reviewed and approved: quote the **range** (9.5-58.2% wall-clock reduction
> across four measured scenarios), never the test-count reduction (57.5-98.9%) restated as a
> runtime saving — they are different measurements.

- `app/analysis/impact.py` builds a source-file → tests map from stored per-test coverage
  contexts (unioned across all runs), then selects tests for a set of changed files.
  `POST /repos/{id}/impact` and `GET /repos/{id}/impact/graph` expose it.
- **The graph is not a traversal.** Coverage observes real execution, so if a test calls
  `foo()` which calls `bar()` in another module, coverage already records that test against
  lines in *both* files — the transitive closure is already flattened into a one-hop lookup.
  Accurate for code that ran, blind to code that didn't.
- **Conservative fallbacks** (why the savings aren't larger, and deliberately so): falls back
  to the full suite when a config/infra file changed (`conftest.py`, `requirements.txt`, ...),
  a changed source file has no coverage data, or a changed test file has no recorded tests.
- **Safety verification**: `scripts/verify_selection.py` breaks a real source file, runs the
  full suite, and checks every actually-failing test was in the selection. 3/3 scenarios,
  **zero missed failures**.
- **Benchmark** (median of 9 interleaved reps, no coverage instrumentation, quiet machine,
  `app/data/benchmark_results.json`, served via `GET /benchmark`). Full suite 2.12s ±0.04s, of
  which **47% is fixed pytest startup/collection** — an irreducible floor:

  | changed file | tests selected | test-count cut | wall-clock cut | execution-time cut |
  |---|---|---|---|---|
  | `toolz/dicttoolz.py` | 52/186 | 72.0% | 42.4% | 90.7% |
  | `toolz/itertoolz.py` | 58/186 | 68.8% | 9.5% | 31.3% |
  | `toolz/functoolz.py` | 79/186 | 57.5% | 23.9% | 66.6% |
  | `toolz/recipes.py` | 2/186 | 98.9% | 58.2% | 99.0% |

- **Reproducibility**: two independent passes agree to within **1.0 percentage point** on every
  scenario. This took two attempts — the first check disagreed by **24 points** because the
  comparison run wasn't isolated (background load, block-measured arms letting machine drift
  land on one side). Fixed by interleaving arms round-robin on an idle machine, not by
  discarding the inconvenient run.
- **How to read these honestly**: test-count cut and wall-clock cut are not interchangeable —
  `itertoolz` cuts 69% of tests but only 9% of wall-clock, because the tests it keeps are the
  slow ones. An earlier benchmark draft reported ">100% of reducible time captured" (impossible)
  from a real methodology bug — a global `--collect-only` floor isn't valid when passing
  explicit node ids, since pytest then collects fewer files. Fixed by measuring overhead per
  arm. The defensible headline is the range, not the best-case scenario alone.

### Phase 5 — Failure Clustering + LLM Summary
- **Seeded bugs**: 4 real, deterministic logic bugs (not flaky) in a separate clone
  (`toolz-bug-seed`, `seeds/bugs/*.py`): `dicttoolz.merge()` drops the last dict (off-by-one),
  `itertoolz.unique()` never marks items seen (duplicates leak through), `itertoolz.first()`
  skips the real first element, `functoolz.identity()` returns `None`. Two bugs deliberately
  share one file (`itertoolz.py`) as a stress test for whether clustering separates co-located
  root causes. Result: 25 failures per run from 4 bugs.
- **Why message-text clustering was rejected, with measurements** (not assumed): `difflib`
  similarity between two failures of the *same* bug (`merge()`, different dict shapes) scored
  0.41-0.74, while two failures from *different* bugs scored as high as 0.75 — text similarity
  doesn't reliably separate same-bug from different-bug. An exact-match normalized-signature
  approach fared even worse: 25 failures fragmented into 20 near-singleton clusters.
- **What works: reusing Phase 4's dependency graph.** `app/analysis/clustering.py` clusters by
  (a) which source files the failing test is known to cover, per the *clean baseline's*
  coverage graph (not the buggy run's own — see `baseline_repo_id` below), and (b) the
  innermost function name pytest's assertion rewriting captures when present
  (`where 1 = first(...)`), a much stronger signal when available. Verified live: 75 failures
  (3 runs × 25) → 12 clusters; the two largest (18 and 6 failures) cleanly and exclusively
  capture the `merge` and `identity` bugs.
- **Known, tested limitation**: failures lacking a "where" hint fall back to file-level
  grouping alone, so `unique()` and `first()` failures without a captured call land in one
  shared `itertoolz.py` cluster instead of two. Tests whose coverage footprint differs by even
  one incidental file form their own smaller cluster instead of joining the main one for the
  same bug — real fragmentation, not a false root cause.
- Endpoint: `GET /repos/{id}/failure-clusters` (`?run_id=`, `?baseline_repo_id=`).
- **LLM layer**: `app/analysis/summarize.py`, one call per cluster via `gemini-3.5-flash`
  (Google Gemini — this project's own choice of LLM provider, independent of which Claude model
  built each phase). Single call, no retries/agent loop/RAG, per the roadmap's locked scope.
  (`gemini-2.5-flash` 404s as "no longer available to new users" despite being listed by the
  SDK; `gemini-3.5-flash` works.)
- **Endpoint**: `POST /repos/{id}/failure-clusters/summarize` (`?min_cluster_size=2&
  max_clusters=10`) — deliberately a `POST` with cost-bounding params, never the free `GET`
  report, since this spends real money per call. Automated tests mock `summarize_cluster`
  entirely — zero real API calls in the suite.
- **Verified live** (2 real calls): the `dicttoolz.py` cluster (18 failures) got an accurate
  "dropped data / wrong return value in merge" hypothesis, matching the seeded bug exactly. The
  `itertoolz.py` cluster (the one clustering couldn't split) still got a correct, specific
  hypothesis ("off-by-one... first element skipped") purely from the representative failure
  text, without being told which bug was seeded — the LLM partially compensated for the
  clustering algorithm's known limitation.
- **Prompt design**: real evidence only (files, test names, one representative message, the
  call-hint if present); asks for a hypothesis, never told the ground truth; told to say
  "evidence too thin" rather than invent a cause.
- Also fixed: the replay harness wasn't passing `--color=no`, so ANSI escape codes were leaking
  into stored failure messages — would have broken clustering and any LLM prompt built from
  that text.

### Phase 6 — CI/CD, Docker, Platform's Own Test Suite
- **Coverage gap-filling** (real gaps, not busywork): baseline was 88%, concentrated exactly
  where Phases 3-4 were verified live via `curl` but never got real pytest coverage
  (`app/api/impact.py` 52%, `app/api/flakiness.py` 63%). Added 33 tests covering every endpoint
  branch, several real edge cases (JUnit's empty-`<testsuites>` error path, coverage-only
  ingestion, `build_dependency_graph`'s `commit_sha` filter — unreachable from any endpoint,
  only unit-testable directly), and a full end-to-end pipeline test (create repo → ingest 5
  runs → flakiness → impact → clustering, all through the public API only). Landed at 98%+
  branch coverage, 109 tests. Remaining gap deliberately not chased: `get_db()` (overridden by
  test fixtures by design) and the real Gemini API call (never exercised automatically).
- **Docker**: `Dockerfile` (python:3.14-slim), `docker-entrypoint.sh` (runs `alembic upgrade
  head` then starts uvicorn), `docker-compose.yml` (app + Postgres 18), `.dockerignore`.
  Verified working end-to-end via `docker compose up --build` — see the Postgres 18 volume
  mount gotcha above for the one real bug hit getting there.
- **Lint**: `ruff` (`pyproject.toml`), `B008` disabled project-wide (flags FastAPI's
  `Depends(get_db)` as a bug — it isn't). Started at 19 findings after enabling rules, narrowed
  the rule set once (Pylint's magic-value-comparison was noise on test literals), landed on 5
  real findings, all fixed (unsorted imports, one unused test variable, two `subprocess.run`
  calls made explicit about `check=False`).
- **CI** (`.github/workflows/ci.yml`): lint + test on every PR/push, no Postgres service needed.
  **Deploy** (`.github/workflows/deploy.yml`): validates the Docker build on GitHub's runners;
  actual deployment is Render's native GitHub auto-deploy (chosen over Fly.io/Railway — same
  host as ChurnGuard, zero GitHub Actions secrets needed for this setup).
- **Coverage config**: `.coveragerc` (branch coverage) + `pytest.ini` (`--cov-fail-under=90`).
- **Deployed and confirmed live on Render.**

### Phase 7 — Dashboard + Final Benchmark Writeup
- **Dashboard** (`dashboard/`): React + TypeScript + Vite. Four views, all real data via the
  API: run history, flaky tests (stat tiles + table, explains the classification rule inline),
  impact analysis (interactive — enter changed files, calls the real endpoint), benchmark
  (grouped bar chart + table over the real Phase 4 numbers).
- Backend additions: CORS enabled (permissive — no auth yet, documented limitation) so the
  dashboard can call the API cross-origin; `GET /benchmark` serves Phase 4's real results,
  committed as a snapshot (`app/data/benchmark_results.json`) rather than recomputed per
  request, since the actual methodology takes minutes and isn't something to redo per page load.
- **Chart colors** from a validated categorical palette (dataviz design process) — checked with
  `scripts/validate_palette.js` against both light and dark surfaces, not chosen by eye. One
  slot (aqua) sits below 3:1 contrast on light by design, which is why the benchmark page ships
  a table view alongside the chart rather than relying on the chart alone.
- Two oxlint rules (`react-hooks/exhaustive-deps`, `react/only-export-components`) disabled
  project-wide in `dashboard/.oxlintrc.json` — both fire on legitimate small-project patterns
  (a generic data-fetch hook with explicit deps; a context+provider pair in one file), same
  judgment call as `B008` on the Python side.
- Verified: `tsc` type-checks clean, oxlint clean, production build succeeds, and manually
  confirmed working end-to-end against the real API (all 4 views render real data).
- DEVELOPER_GUIDE.md consolidated into this final pass — reorganized chronologically, merged a
  duplicated Phase 5 section, updated the stale future-tense project description, added the
  dashboard and Docker/CI/CD components that were missing.

## What you should understand, edit, or review

- The **Human Edit** section in the roadmap PDF for each phase — your own framing of decisions,
  useful for interview prep.
- The database password (`ci_brain`/`ci_brain`) is a local-dev-only placeholder in
  `app/config.py`'s default. Fine for a laptop-only Postgres instance; would need to move to
  `.env` (already gitignored) before this ever touches a shared or public environment.
- Git identity for this repo is `Som0111` / `soumyaswarup07@gmail.com`, matching ChurnGuard, so
  commits attribute correctly to your GitHub account.
- The benchmark writeup (`docs/BENCHMARK.md`) and resume line are reviewed and approved.

## Troubleshooting notes

- `sqlalchemy.exc.OperationalError: no such table` in tests → the SQLite in-memory test DB
  needs `poolclass=StaticPool`, otherwise each new connection gets its own throwaway database.
  Already fixed in `tests/conftest.py`; noting it here in case it resurfaces in a future test
  file.
- Getting `Internal Server Error` back with no detail from a running `uvicorn` process → check
  `uvicorn`'s own console/log output, not just the HTTP response; FastAPI doesn't leak
  traceback details to the client by default.
- Dashboard shows empty states everywhere → check the API is actually running and reachable at
  `VITE_API_BASE` (default `http://localhost:8000`), and that at least one repo has ingested
  run data (`scripts.replay_harness`).

## Hardening: ingestion (P0 item 1)

- `POST /repos/{id}/runs`: uploads are read with a cap (`MAX_UPLOAD_BYTES`, default 25 MB) and
  rejected with 413 beyond it; `commit_sha` (`[A-Za-z0-9._-]{1,40}`) and `branch` (<=255, no
  control chars) are validated (400); empty strings are stored as NULL.
- JUnit: duplicate `classname::name` -> 400 (parametrized ids differ, so are fine); negative/NaN/inf
  `time` -> 400; entities are not resolved. Coverage JSON: `NaN`/`Infinity` -> 400.
- `TestCase` creation uses a savepoint and re-fetches on `IntegrityError` (lost race). Any other
  DB error rolls back the whole run and returns 503 with a generic message.
- Verified: 134 tests pass (97.7% coverage), ruff clean on `app/ tests/`.
- Not done: real concurrent-request test (race is simulated), Postgres-specific check (item 6).

## Hardening: API validation (P0 item 2)

- Error shape is always `{"detail": ...}`: string for HTTP errors, list of `{loc, msg}` for 422
  (input values are not echoed), generic `"internal server error"` for unhandled 500s (logged server-side).
- `RepoCreate`: name trimmed, 1-255; url trimmed, <=500, blank -> null. Duplicate create (incl. DB-level
  race) -> 409.
- `POST /repos/{id}/impact`: `changed_files` must have 1-1000 entries of 1-1000 chars. **Contract change:**
  an empty list is now 422 (was 200 with 0 selected tests). Final no-op semantics are item 3.
- Failure clusters: `run_id`/`baseline_repo_id` >= 1; `run_id` must belong to the repo (404); baseline must exist
  (404) and share at least one test node id with the repo (400); `min_cluster_size` 1-1000, `max_clusters` 1-50.
- Ingest endpoint documents 400/404/413/503 in OpenAPI. Other endpoints' schemas were generated from their
  Pydantic models and left as-is; I checked only the ingest and error shapes, not every endpoint by hand.
- Verified: 157 tests pass, ruff clean on `app/ tests/`.

## Hardening: test-impact safety (P0 item 3)

- `normalize_path` now collapses `./`, `//`, `a/../b`; `in_repo_path` rejects absolute, drive-letter,
  `../`-escaping and vendored (`site-packages`, `node_modules`, `venv`...) paths. Coverage edges for such files are
  dropped; a *changed* file like that forces the full suite (never aliased to a repo file).
- Coverage contexts that don't look like `x.py::[Class::]test` map to the `UNMAPPED_CONTEXT` marker. Any selected
  set containing an id with no stored `TestCase` (marker, renamed test, mapping mismatch) -> full-suite fallback.
- `select_tests([])` now returns the full suite with `full_suite_fallback=True` (was: empty). The HTTP API rejects
  an empty list with 422 first (item 2), so CI cannot read "nothing changed" as "run nothing".
- Tests: `tests/test_impact_safety.py` (setup/teardown, nested classes, parametrized, Windows paths, hostile paths,
  unmapped contexts, mixed known/unknown files).
- Checked against the real `replay_data/bug_run_1` and `flaky_run_1` coverage+JUnit: 0 unmapped contexts, 0
  unmatched ids, selections unchanged (e.g. functoolz 79/186), so the new fallbacks do not erode the benchmark.
- NOT re-run: `scripts/verify_selection.py` (needs the cloned target repos + live DB). The select logic only became
  more conservative, but the injection run itself is unverified after this change. Paths are case-sensitive;
  Windows case-insensitivity is not handled (falls back to full suite, the safe direction).

## Hardening: dashboard API config (P0 item 4)

- `dashboard/src/lib/http.ts` (new, no Vite globals) holds the request helper: trailing slashes on
  `VITE_API_BASE` are normalised; `Content-Type: application/json` is only set for string bodies (FormData is left to
  the browser); empty/204 bodies return `undefined`; non-JSON success bodies and network failures throw `ApiError`
  (status 0 = never reached the API); `AbortError` passes through for cancellation (item 13).
- `npm test` runs `src/lib/http.test.ts` with Node's built-in runner (7 tests, no new dependency; test files are
  excluded from the app tsconfig). No component-level tests exist.
- **Dashboard is not deployed** - only the API is (README/`dashboard/README.md` now say so). `VITE_API_BASE` is a
  build-time variable.
- `docker-entrypoint.sh` now binds `${PORT:-8000}` instead of a hard-coded 8000 (Render injects `PORT`). Unchanged
  behaviour when `PORT` is unset.
- **Render audit - not done, cannot be from here:** I have no access to the Render dashboard, so I could not verify
  which env vars (`DATABASE_URL`, `GEMINI_API_KEY`, maybe `PORT`) are actually set or the service's start command /
  port. Please confirm in Render: Docker runtime, no custom start command overriding the entrypoint, `DATABASE_URL`
  and `GEMINI_API_KEY` present, and note the value of `PORT` if you set one.

## Hardening: resource limits, API key, LLM safety (P1 item 5)

- **Config (env):** `CORS_ORIGINS` (comma list, default `*`), `API_KEY` (default unset), `MAX_UPLOAD_BYTES`,
  `MAX_RESULTS_PER_RUN` (50 000, 413), `GEMINI_TIMEOUT_SECONDS` (15).
- **Decision taken (revisit if you disagree):** `API_KEY` is optional. When set, `POST /repos`, `POST /repos/{id}/runs`
  and `POST .../failure-clusters/summarize` need an `X-API-Key` header (constant-time compare, `app/security.py`);
  GETs and `/impact` stay open. When unset the API is fully open - **which is how the public Render deployment
  behaves until you set `API_KEY` there** (and then pass `CI_BRAIN_API_KEY` to `scripts/replay_harness.py`).
  Wildcard CORS is still the default; CORS is not authentication.
- **LLM cost bounds:** `max_clusters` now 1-20 (was 1-50), one Gemini call per cluster, summarize is POST-only
  and key-guarded when configured.
- **Gemini:** explicit 15 s timeout; `SummarizerError` with actionable messages for 429/404/401-403/other API
  errors, timeouts/network errors and empty responses; reported per cluster in `llm_error`, never a 500, and the
  free GET cluster endpoint is unaffected. Response text bounded to 1000 chars; only status code / exception type
  is logged (never keys, SDK messages or uploaded content).
- **Prompt injection:** instructions moved to a system prompt that declares everything in `<cluster_data>` to be
  log data and to ignore instructions inside it; uploaded text is stripped of `<cluster_data>` tags so it cannot
  escape the block. This is mitigation, not a guarantee - the output is still shown as a *hypothesis*.
- A bug found by the new test: the Gemini client was constructed outside the error handling; fixed.
- **Secrets scan:** tracked files contain only `.env.example` files; a pattern scan for Gemini/OpenAI-style keys
  over tracked files found nothing. Not scanned: git history.
- Not verified: a real Gemini call after the prompt restructure (tests mock the SDK; no API key used here).
- Verified: 216 backend tests pass, ruff clean on `app/ tests/`.

## Hardening: database lifecycle & migrations (P1 item 6)

- **Audit result:** FKs, unique `(repo_id, node_id)`, enums (migration and model use the same lowercase values)
  and indexes already matched the schema; no other changes were justified by actual queries (index review is
  item 11). Only invariant added: `CHECK (duration_seconds IS NULL OR duration_seconds >= 0)`.
- **Migration `0002`** adds it (batch mode, so SQLite works too). It first NULLs any negative duration so the
  constraint can't fail on old data (the API has rejected them since item 1). Downgrade drops it. Also escaped `%`
  in `DATABASE_URL` for `alembic/env.py` (configparser would choke on a `%` in a password).
- **Cascade:** deletion cascades through the ORM (`delete-orphan`), tested; the DB FKs have no `ON DELETE CASCADE`,
  so raw SQL `DELETE FROM repos` fails on FK rather than orphaning rows. No delete endpoint exists, so I did not
  change FKs. Note SQLite does not enforce FKs by default, so the fast tests can't catch FK violations.
- **Startup:** `docker-entrypoint.sh` logs `[entrypoint]` messages and, if `alembic upgrade head` fails, prints
  FATAL and exits 1 without starting the server (container exits non-zero; Render shows it in Logs).
- **Tests:** `tests/test_migrations.py` - fresh upgrade, model-vs-migration drift check (`compare_metadata`),
  downgrade to base, upgrade from the `0001` schema with data, CHECK + UNIQUE enforcement, ORM enum/JSON round-trip
  and cascade. Runs on SQLite always; the **same tests run on PostgreSQL when `TEST_POSTGRES_URL` is set** (it
  drops the `public` schema - use a throwaway DB).
- **NOT verified on PostgreSQL:** the Docker daemon wasn't running here and no local Postgres exists, so only the
  SQLite half ran (4 passed, 4 Postgres variants skipped). To run it: start Docker Desktop, `docker compose up -d db`,
  create a `ci_brain_test` DB, then
  `set TEST_POSTGRES_URL=postgresql+psycopg2://ci_brain:ci_brain@localhost:5432/ci_brain_test` and
  `.venv\Scripts\python.exe -m pytest tests/test_migrations.py`. Wiring it into CI is item 7.
- Heads-up: run tests with `.venv\Scripts\python.exe` - the global Python lacks `alembic`, where the local
  `alembic/` directory then shadows the package as a namespace package and imports fail confusingly.
- Prod: migration `0002` has not been applied to Render's DB; it will run on the next deploy via the entrypoint.

## Hardening: CI, Docker, deploy workflow (P1 item 7)

- **`ci.yml`** now has four jobs: `lint-and-test` (ruff + pytest with the 90% coverage floor),
  `postgres-migrations` (a `postgres:18` service; runs `tests/test_migrations.py` with `TEST_POSTGRES_URL`, coverage
  floor disabled for that single file), `dashboard` (`npm ci`, build, lint, `npm test`, Node 24) and
  `docker-compose-smoke` (`docker compose up --build`, polls `/health`, asserts the `migrations OK` log line, tears
  down). Top-level `permissions: contents: read` and per-ref `concurrency` with cancel-in-progress; the deploy
  workflow got the same two settings (its only job is still just `docker build` - Render does the actual deploy).
- **Python version:** left at 3.14 in all three places (CI, `python:3.14-slim`, local venv 3.14.6). The pins in
  `requirements.txt` were resolved on 3.14 and I could not test 3.11/3.12 here, so I did not move it.
- **Actions** are pinned to major tags (`checkout@v4`, `setup-python@v5`, `setup-node@v4`), not commit SHAs.
- **Dockerfile:** runs as non-root `appuser` (uid 10001; the app writes nothing to disk), `PYTHONUNBUFFERED`
  for logs, `HEALTHCHECK` hitting `/health` on `$PORT`. No secrets in layers (env only at runtime).
- **Coverage policy:** floor is 90% (`pytest.ini`); actual is ~99%. README says "98%+" - that is a measured
  figure, not the enforced threshold.
- **NOT verified (nothing here was executed):** the Docker daemon is down on this machine, so I could not build the
  image, run it as non-root, try compose up, a migration failure, or a restart; the new workflow jobs have only been
  YAML-parsed, never run on GitHub. Expect to fix small things on the first CI run. Restart behaviour: compose has no
  restart policy, and `depends_on: service_healthy` covers DB readiness only.

## Hardening: logging (P1 item 8)

- Audit: `app/` already had **no `print()` calls** (a test now enforces that); the gap was that logging was never
  configured, so INFO was invisible and `logger.exception` dumped full tracebacks. `app/logging_config.py` sets
  `logging.basicConfig` from `LOG_LEVEL` (default `INFO`; unknown values fall back to INFO) at import of `app.main`.
- Error logs now carry the exception *type* only; tracebacks (which include internal file paths) appear only when
  `LOG_LEVEL=DEBUG`. Uploaded content, SQL parameters, DB error messages and API keys are never logged (tested with
  marker strings). Successful ingests log one INFO line: run id, repo id, result count.
- Scripts keep `print()` for CLI output; the two error-ish messages (`export_db_via_api` fallback warning and
  `verify_selection`'s UNSAFE result) now go to stderr. Other scripts' prints are plain progress output.
- Not done: no request-access logging or JSON format (uvicorn's own access log is unchanged); the Render
  `LOG_LEVEL` is unset, so it defaults to INFO.
- Verified: 226 tests (4 Postgres skips), ruff clean on `app/ tests/`.

## Review: flakiness classification & confidence (P1 item 9)

- **Commit scoping:** unscoped `GET /repos/{id}/flakiness` still pools every JUnit run (changing it would silently
  change verdicts on your live data, where all replay runs share one pinned commit). New response fields
  `commits_seen` and `warning` now flag pooled results that span several commits, or mix in runs with no
  `commit_sha`; `?commit_sha=` scopes the report. The code does not itself decide which commit is "right".
- **Skips:** verified excluded from the pass/fail denominator, `fail_rate` and the `MIN_RUNS=5` gate; `error`
  counts as a fail. Boundaries (0/1/all-skipped/4-vs-5 runs, minority 1/2/3) are now tested.
- **Confidence meaning** (documented in `classify.py` and OpenAPI): minority-outcome count (>=3 high, 2 medium, 1
  low). It is an evidence-strength heuristic, not a probability or significance test; `quarantine` = flaky at
  high/medium. Labels/values were not renamed, to avoid breaking the dashboard.
- **Idempotency:** new optional form field `run_key` on `POST /repos/{id}/runs` (unique per repo, migration
  `0003`). Re-sending the same key returns **200** with the original run and `duplicate: true`, storing nothing
  (race-safe via the unique constraint). Uploads *without* a key are never deduplicated - I deliberately did not
  hash content, because identical files are legitimate in synthetic/fast suites (and in this repo's own tests).
  CI should pass e.g. `$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT` (same attempt retried -> same key). `replay_harness`
  does not send one yet. `IngestResult` gained `duplicate`; creation still returns 201.
- Not done: no real significance test (e.g. binomial/Wilson interval); per-commit stratified verdicts.
- Verified: 247 passed, 4 skipped (Postgres), ruff clean; migration drift test covers `0003` on SQLite only.

## Review: clustering explainability & LLM robustness (P1 item 10)

- **Heuristic vs evidence, in the API:** both cluster reports carry a `note` ("heuristic groupings, NOT confirmed
  root causes"). OpenAPI descriptions mark `covered_files` / `call_hint` / `representative_message` as OBSERVED and
  `hypothesis` as MODEL-GENERATED. New per-cluster fields: `distinct_tests` (`size` counts failure *records*, so a
  test failing in 3 runs adds 3 unless you pass `run_id`) and `has_coverage` (false = grouped by hint only).
- **Bounds:** JUnit failure text is capped at 20 000 chars at ingest (`[truncated]`); `fetch_failures` also
  `substr`s old rows; responses truncate `representative_message` to 2000. Hint extraction stays fast on
  pathological input (tested). Empty-response/`None` handling and the 1000-char hypothesis cap came with item 5.
- **LLM:** clusters whose representative message is empty are not sent to the model (`llm_error` explains);
  Gemini failures are per-cluster and leave the free `GET` endpoint untouched (tested).
- **Fragmentation check (no heuristic change):** replaying `replay_data/bug_run_{1,2,3}` junit against a graph built
  from the single run `flaky_run_1` gives 25 failures -> 12 clusters each time (largest 6, 5, 3, 2, 2, then
  singletons) for the seeded bugs. That graph is one run, not the unioned DB graph, so this overstates the
  fragmentation of a live deployment; exact covered-file sets do split a bug whose failing tests touch different
  extra files. I did not alter the clustering rules; any change should be judged against the seeded tests first.
- **Found while testing:** the new "no Gemini key" test made a **real Gemini call**, because `.env` holds a real key
  and settings load it in tests. `tests/conftest.py` now has an autouse fixture that blanks `gemini_api_key` for
  every test (tests needing a key set their own). One real call was made on this machine before the fix.
- Verified: 261 passed, 4 skipped (Postgres), ruff clean.

## Performance on larger histories (P1 item 11)

- **Measured first** (synthetic: 1 repo, 100 runs x 400 tests, 60 coverage files per run; SQLite in memory, timings
  taken under `tracemalloc` so absolute numbers are inflated - compare before/after only):

  | endpoint | before | after |
  |---|---|---|
  | `GET /runs` | 1326 ms, 97.6 MB | 85 ms, 1.2 MB |
  | `GET /flakiness` | 1155 ms, 22 MB | 92 ms, 1.0 MB |
  | `POST /impact` | 15 634 ms, 96.8 MB | 1 554 ms, 8.7 MB |
  | `GET /impact/graph` | 16 495 ms | 1 998 ms |
  | `GET /failure-clusters` | 24 017 ms | 1 691 ms |

  Query counts were already constant (2-4); the cost was Python-side. Probe script was a throwaway (not committed).
- **Causes & fixes:** (1) `TestRun.coverage_data` (megabytes of JSON) was loaded for every run on any run query ->
  column is now `deferred`, and the graph builder selects only that column and streams it (`yield_per`);
  (2) per-run context normalisation was repeated for every line -> pure `normalize_test_id`/context mapping is
  `lru_cache`d (a pure-function memo, not a data cache, so no invalidation concern); (3) flakiness built one Python
  object per stored result -> now a single SQL `GROUP BY` with conditional sums; (4) test-id lookups select columns
  instead of entities.
- **Pagination:** `GET /repos/{id}/runs` and `/tests` take `limit` (default 500, max 1000) and `offset`, return the
  same list shape, plus an `X-Total-Count` header (exposed through CORS). **Behaviour change:** more than 500 runs
  now truncates to the newest 500 by default; the dashboard does not yet show a "truncated" hint (item 12).
  `GET /runs/{id}` still returns all results of one run (bounded by `MAX_RESULTS_PER_RUN`).
- **Index:** migration `0004` adds `(repo_id, commit_sha)` on `test_runs` (used by the commit filters); a test checks
  SQLite's query plan uses it. Other filters were already indexed; I added nothing else.
- **Tests:** `tests/test_performance.py` asserts query counts do not grow with history (2 vs 25 runs, all six heavy
  endpoints), pagination/headers, that listing runs never selects `coverage_data`, and the index plan.
- **Remaining limits:** impact/clusters still cost O(number of runs x coverage size) per request (1.5 s at 100 runs
  here); a precomputed/cached graph would fix that but needs invalidation on ingest, which I deliberately did not
  build. `export_db.py` reads `coverage_data` lazily per run (N+1, fine for a one-off export). Postgres timings were
  not measured.
- Verified: 274 passed, 4 skipped (Postgres), ruff clean on `app/ tests/`.

## Dashboard states & freshness (P2 item 12)

- **Stale data fixed at the source:** `useApiData` now tags each result with the deps it was fetched for and only
  returns it while those still match, so switching repos never shows the previous repo's data for a frame, and late
  responses for old selections are ignored. It also returns `errorStatus` and `reload()`.
- **Errors:** `ErrorState` distinguishes "Can't reach the API" (status 0, plus a hint when a deployed build still
  points at localhost, i.e. `VITE_API_BASE` was not set at build), HTTP 4xx, HTTP 5xx and generic failures, and has a
  **Retry** button (pages, repo list and benchmark). "No data ingested yet" remains a separate empty state; a repo
  list that is empty gets its own message ("No repositories exist on the API yet").
- **Impact page** is remounted per repo (`key`), so a typed query, result or error from the previous repo can't
  linger or be overwritten by a late response.
- **Runs page** reads `X-Total-Count` and says "Showing the newest N of M runs" when the list is truncated (item 11).
  **Flakiness page** shows the API `warning` (mixed commits, item 9) and explains that confidence is an evidence
  label, not a probability. (Cluster/"heuristic" wording from item 10 has no dashboard page to live on yet.)
- **Formatting:** `lib/format.ts` (percent, duration, count, timestamp; unit-tested) used by all pages; long test ids
  wrap and carry a `title`; commit shas show 8 chars with the full value in `title`.
- **Accessibility/responsive:** table `scope`/captions, `role="alert"` / `role="status"` on states, chart wrapped
  with an `aria-label` and the existing table view as the text alternative (pills carry text, not colour alone),
  visible keyboard focus outline, wrapping top bar on narrow screens.
- **Verified:** `npm test` 11 passed, `npm run build` (tsc) and `npm run lint` clean. **Not verified:** no browser
  was run (the Playwright MCP server failed to connect), so layout, narrow-screen behaviour, focus order and the
  hook's repo-switch behaviour have not been seen on screen; there is no React test tooling, so `useApiData` has
  no automated test. Worth a manual pass: switch repos quickly, stop the API and hit Retry, resize to ~400px.

## Dashboard fetch lifecycle (P2 item 13)

- **Call-site audit:** `Runs`, `Flakiness` and `Impact` fetchers close over `selectedRepoId` only (key
  `[selectedRepoId]`); `Benchmark` closes over nothing (key `[]`). The key lists every value each fetcher uses, so
  the project-wide `react-hooks/exhaustive-deps: off` is not hiding a stale closure today. The rule remains off
  (see `.oxlintrc.json`); the contract is documented on `useApiData`: *the fetcher may only depend on values in its
  key*. The second parameter is now typed `QueryKey` (primitives only) instead of `unknown[]`.
- **Cancellation:** fetchers receive an `AbortSignal` (all `api.*` methods accept one and pass it to `fetch`). The
  effect cleanup aborts the in-flight request when the repo changes or the component unmounts; the repo-list
  load in `RepoContext` and `Impact`'s analyze request (superseded by a newer submit, aborted on unmount/repo
  switch) do the same. An aborted request can never write state, and `AbortError` is not shown as an error.
- **Race-safety core extracted to `lib/startFetch.ts`** (no React) and unit-tested: tagged results, cancel
  suppresses late success *and* late failure, overlapping fetches (only the latest reports), error status mapping,
  synchronous throws, fetchers that ignore the signal. 18 dashboard tests now pass (`npm test`).
- Kept from item 12: results are tagged with the key they were fetched for, so loading/error/data cannot show a
  previous selection's state.
- **Not covered:** the thin React wrapper (`useApiData`'s `useState`/`useEffect` wiring) still has no automated test
  (no React test tooling; adding one was judged not worth a new dependency), and nothing was run in a browser.

## Benchmark reproducibility audit (P2 item 14)

- **Re-checked against checked-in artifacts (no measurement re-run):** the `docs/BENCHMARK.md` table equals
  `app/data/benchmark_results.json` row for row; the "two passes within 1.0 pp" claim holds (max gap 1.0 pp, local
  `replay_data/bench_A/B.json`); fixed overhead is 46.7% (0.989/2.12 s); 186 tests; pinned commit matches
  `scripts/clone_target.py`. `docs/BENCHMARK.md` now has a claim -> command -> status table.
- **Found & fixed:** (1) the docs told you to run the benchmark with `--reps 5` but the published numbers are 9
  reps -> docs say `--reps 9` (script default is still 5); (2) `verify_selection.py` failure-injected only 3 of the 4
  benchmarked files - `recipes.py` was missing, so the "never drops a failure across all measured scenarios" resume
  wording overreached. Added a `recipes.py` scenario (**not run**) and a test that benchmark and verify scenarios
  cover the same files; (3) results carried no environment info -> `benchmark_impact.py` now writes an
  `environment` block (UTC time, commit, OS, CPU count, Python). The committed artifact predates that and cannot be
  back-filled honestly.
- **Not changed, your call:** the approved resume line. `docs/BENCHMARK.md` flags the over-claim next to it; either
  re-run `python -m scripts.verify_selection` (needs the target clones + a DB holding the baseline runs) or narrow
  the wording to the 3 verified files.
- **Not re-run / not reproducible here:** `verify_selection`, the flaky-detector 4/4 result and the 75->12 clustering
  figures (all need the live DB / target clones), and the two Gemini outputs (external, non-deterministic).
- **Synthetic vs real** is stated in every section of `docs/BENCHMARK.md` already; unchanged.
- **Script smoke tests:** `tests/test_scripts_smoke.py` imports every tracked script and checks `--help` exits 0 for
  those with a CLI. The checklist's `seed_test_data.py` does not exist (`apply_seed.py` is the equivalent). Full
  runs (cloning, benchmarking, DB export) are deliberately not exercised in tests.
- Verified: 295 passed, 4 skipped (Postgres); ruff clean on `app/ tests/` and the two edited scripts.

## Dependency & repository hygiene (P2 item 15)

- **Ignore rules:** `.gitignore` now also covers `*.log`, `logs/`, `.ruff_cache/`, `.env.*` (except `.env.example`),
  `.claude/`, coverage XML/data variants (previously `gen_run2.log`-style files showed up as untracked).
  `.dockerignore` additionally excludes `dashboard/`, `exports/`, logs and the ruff cache (smaller build context).
  Already covered before: venvs, caches, `node_modules`, `dist`, `*.db`, `target_repos/`, `replay_data/`, `.env`.
  Not ignored on purpose: your untracked `raw_evalforge_export.jsonl` and `scripts/_gen_evalforge_raw.py` (yours to
  commit or delete; the script fails 4 ruff rules, which is why it is not in the lint set I vouch for).
- **Secrets / artifacts:** tracked files contain only `.env.example` files; no key-shaped strings in tracked files
  (git history not scanned). The one large tracked artifact is `exports/ci_brain_render_export_2026-08-16.json`
  (324 KB, a deliberate partial export of the live DB): scanned - no emails, tokens or local paths in it.
- **Version alignment:** Python 3.14 in Docker (`python:3.14-slim`), CI (`3.14`) and the local venv (3.14.6);
  `requirements.txt` is a fully pinned lockfile resolved on 3.14. `pyproject.toml` only configures ruff (no
  `requires-python`); `pytest.ini` (coverage floor 90%) and `.coveragerc` (what to measure) are complementary, not
  duplicates. Dashboard: `npm ci` works against the committed lockfile (run in CI and in this audit).
- **Unused dependencies (reported, NOT removed):** nothing imported by the code is missing, and every package the
  code imports is listed. Packages that no other pinned package requires and the code never imports:
  `httptools`, `watchfiles`, `PyYAML` (the `uvicorn[standard]` extras: faster HTTP parsing / `--reload` / YAML log
  config) - harmless but not needed on Render; `pytest`, `pytest-cov`, `ruff`, `coverage` are dev tools that ship in
  the Docker image because there is a single `requirements.txt`. Splitting a `requirements-dev.txt` would shrink the
  image but changes CI and Docker installs, which I cannot test here (Docker is down), so I left it.
- **No dependency upgrades were made** (none found incompatible or necessary for a fix). `npm audit` flagged 1 high (transitive `source-map-js`, a build-time DoS in source-map parsing);
  `npm audit fix` bumped just that lockfile entry (see `git diff dashboard/package-lock.json`), after which
  `npm ci`, build, lint and 18 tests pass and `npm audit` reports 0 vulnerabilities.

## Final verification record (hardening checklist, 2026-10-17)

Commands actually run at the end, with results:

| Check | Result |
|---|---|
| `ruff check app/ tests/ scripts/` | 4 errors, **all in untracked `scripts/_gen_evalforge_raw.py`** (not part of this work); `app/` and `tests/` clean |
| `pytest` (coverage floor 90%) | 295 passed, 4 skipped (PostgreSQL variants), 98.13% |
| `cd dashboard && npm ci && npm run build && npm run lint && npm test` | all pass; 18 tests; `npm audit`: 0 vulnerabilities |
| OpenAPI (`/openapi.json`) | 14 operations; documented error codes now match what the handlers return (400/401/404/409/413/503). Caveat: the generic 422 body in the schema is FastAPI's default (`loc`, `msg`, `type`); our handler returns `loc`+`msg` only (a subset) |
| Docker build / compose smoke / restart / migration-failure | **not run** - Docker daemon not running on this machine |
| PostgreSQL migration smoke (`TEST_POSTGRES_URL`) | **not run** - no Postgres available; wired into CI (`postgres-migrations` job) |
| `scripts.verify_selection` / benchmark | **not re-run** (need target clones + DB); see P2-14 notes |
| `git diff` review | 49 modified + 22 new files (no commits made; HEAD is still `a93464e`); no secrets, `.env`, debug statements or large artifacts found by pattern scan |

Behaviour/API contract changes (also noted per item above): empty `changed_files` -> 422; duplicate JUnit testcases,
negative/NaN durations, bad `commit_sha`/`branch`/`run_key` -> 400; oversized uploads / too many results -> 413;
DB failure during ingest -> 503; `max_clusters` capped at 20; `GET /runs` and `/tests` paginated (default 500);
new response fields (`duplicate`, `commits_seen`, `warning`, cluster `note`/`distinct_tests`/`has_coverage`);
optional `API_KEY`; migrations `0002`-`0004` (apply on next deploy); `select_tests([])` and unmappable coverage ->
full-suite fallback.

## PostgreSQL & Docker verification (follow-up, 2026-10-17)

Run after Docker Desktop was started; supersedes the "not verified on PostgreSQL / Docker" caveats in the P1-6/P1-7
and final-verification sections above (those described the state before this run).

- `docker compose up --build` (on alternate host ports 18000/15432 because 8000/5432 were taken by other local
  services): both containers healthy, app runs as non-root `appuser`, logs show migrations `0001`-`0004` applied on a
  fresh PostgreSQL 18, `/docs` and `/health` return 200, a live ingest/duplicate-`run_key`/pagination/impact smoke
  worked. `docker compose down -v` left nothing behind.
- Postgres 18.6 container: `alembic upgrade head` -> `downgrade -1` (0004 -> 0003) -> `upgrade head`, and a full
  `downgrade base` -> `upgrade head`, all clean; the CHECK, UNIQUE and index exist afterwards.
- `tests/test_migrations.py` with `TEST_POSTGRES_URL`: 8 passed (4 SQLite + 4 PostgreSQL, including the
  model-vs-migration drift check).
- Still not run: the GitHub Actions workflows on GitHub itself; failing-migration and restart behaviour of the stack.
