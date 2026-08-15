# Continuous Integration (CI) Brain

**Live API: [https://ci-brain.onrender.com](https://ci-brain.onrender.com)** ([`/health`](https://ci-brain.onrender.com/health)
)


You can check that the API is running by opening /health, which should return {"status":"ok"}. Since it's hosted on Render's free tier, it may go to sleep after 15 minutes of inactivity, so the first request after that can take around 50 seconds.

I built this to understand how the test-intelligence tooling used inside large engineering
orgs actually works under the hood — the stuff that decides which tests to run on a diff,
flags a test as flaky instead of just retrying it blindly, and groups a wall of CI failures
into "here's probably what broke." So I built a working version of all three end to end: a
service that ingests test-run data from a Python repo's CI and

- **detects flaky tests statistically** — flags a test when it's produced both a pass and a
  fail on identical code, not just when its fail rate crosses some threshold, and gives a
  confidence level and a quarantine recommendation instead of a flat yes/no,
- **figures out the minimal set of tests to run for a change**, by building a real
  file-to-test dependency graph out of coverage data and falling back to the full suite
  whenever it can't answer confidently rather than guessing,
- **clusters failures by likely root cause** and asks an LLM for a one-line plain-English
  hypothesis per cluster, grounded in the actual evidence rather than told the answer.

To actually test all of this against something real, I benchmarked it against
[`toolz`](https://github.com/pytoolz/toolz), a small real open-source Python library, and
seeded some synthetic flaky tests and synthetic bugs into separate clones of it myself —
`toolz` doesn't come with either on demand, so I wrote them in specifically to have something
for the detector and the clustering to catch. They're clearly labeled as seeded everywhere in
the code and docs; I'm not passing them off as bugs I found in the wild.

Full results and what's real vs. synthetic: [`docs/BENCHMARK.md`](docs/BENCHMARK.md).
Architecture notes and how to run everything: [`HUMAN_GUIDE.md`](HUMAN_GUIDE.md).

## What I found

- Test impact analysis cut **9.5–58.2% of wall-clock runtime** and **57.5–98.9% of tests run**
  across the four scenarios I measured — and I verified it never once dropped a test that
  actually would have caught a regression, by breaking real code and checking the full suite
  against what got selected.
- The flakiness detector caught **4 out of 4** of the flaky tests I seeded, with **zero false
  positives** out of 186 real tests.
- Failure clustering took 75 failures from 4 seeded bugs and grouped them into 12 clusters,
  with the two biggest clusters cleanly isolating two of the bugs by root cause on their own.

## Stack

FastAPI · PostgreSQL + SQLAlchemy + Alembic · pytest (98%+ branch coverage) · React + TypeScript
+ Vite · Google Gemini for the failure summaries · Docker + GitHub Actions · deployed on Render.

## Running it

```
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Or with Docker (spins up Postgres + the app together):

```
docker compose up --build
```

Dashboard (needs the API running above):

```
cd dashboard && npm install && npm run dev
```

`HUMAN_GUIDE.md` has the full setup, the replay harness I used to generate test data, how to
seed the synthetic variants, deployment steps, and everything I hit along the way that wasn't
obvious the first time.

## Layout

```
app/            FastAPI service: ingestion API, analysis (flakiness/impact/clustering/LLM)
scripts/        Replay harness, benchmark runner, safety verification, seed application
seeds/          The synthetic flaky tests + bugs I seeded, tracked in git
dashboard/      React + TypeScript dashboard
docs/           Benchmark writeup and build notes
tests/          110 tests, 98%+ branch coverage
```
