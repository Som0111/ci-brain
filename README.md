# CI Brain

A backend service that plugs into a Python repo's CI and detects flaky tests, predicts the
minimal set of tests to run for a code change (test impact analysis), and clusters test
failures by root cause with an AI-generated summary.

Built as a resume-shortlisting portfolio project targeting Core SDE / SWE internship roles —
see `CI_Brain_Claude_Code_Roadmap.pdf` for the full phase-by-phase plan and `HUMAN_GUIDE.md`
for architecture notes and how to run it.

**Status: Phase 2 of 7 complete** (project scaffold + ingestion API; replay harness against a
real benchmark repo).

## Stack

FastAPI, PostgreSQL + SQLAlchemy + Alembic, pytest, Docker (coming in Phase 6).

## Quickstart

```
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

See `HUMAN_GUIDE.md` for full setup, testing, and troubleshooting instructions.
