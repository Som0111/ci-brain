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
  `verify_selection.py` (empirically proves impact analysis never drops a real failure),
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
.venv\Scripts\python.exe -m scripts.benchmark_impact --reps 5
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
| Run the benchmark | `.venv\Scripts\python.exe -m scripts.benchmark_impact --reps 5` |
| Run everything in Docker | `docker compose up --build` |
| Run the dashboard | `cd dashboard && npm run dev` |

## Known limitations / gotchas

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
