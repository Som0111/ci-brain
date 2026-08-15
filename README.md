# CI Brain

A backend service that plugs into a Python repo's CI and detects flaky tests, predicts the
minimal set of tests to run for a code change (test impact analysis), and clusters test
failures by root cause with an AI-generated summary.

Built as a resume-shortlisting portfolio project targeting Core SDE / SWE internship roles —
see `CI_Brain_Claude_Code_Roadmap.pdf` for the full phase-by-phase plan and `HUMAN_GUIDE.md`
for architecture notes and how to run it.

**Status: Phase 6 of 7 complete** (ingestion API, replay harness, flaky-test detection,
coverage-graph test impact analysis, LLM-assisted failure clustering, Docker, and CI/CD).

## Stack

FastAPI, PostgreSQL + SQLAlchemy + Alembic, pytest (98%+ coverage), Google Gemini (failure
summarization), Docker + GitHub Actions CI/CD, deployed on Render.

## Quickstart

```
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

See `HUMAN_GUIDE.md` for full setup, testing, and troubleshooting instructions.
