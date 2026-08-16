"""Exports the full logical contents of a CI Brain database to JSON.

Unlike the public API (which never returns TestRun.coverage_data - see
app/api/runs.py), this connects directly to the database, so the export
includes coverage data too and is a genuinely complete snapshot, not a
partial one.

The DB URL is read from --database-url or the DATABASE_URL env var, never
hardcoded or written anywhere - only used for the duration of this script.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Repo, TestCase, TestResult, TestRun


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def export(database_url: str) -> dict:
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    Session = sessionmaker(bind=engine)
    db = Session()

    repos_out = []
    for repo in db.scalars(select(Repo).order_by(Repo.id)).all():
        test_cases = db.scalars(
            select(TestCase).where(TestCase.repo_id == repo.id).order_by(TestCase.id)
        ).all()
        runs = db.scalars(
            select(TestRun).where(TestRun.repo_id == repo.id).order_by(TestRun.id)
        ).all()

        repos_out.append({
            "id": repo.id,
            "name": repo.name,
            "url": repo.url,
            "created_at": _iso(repo.created_at),
            "test_cases": [
                {
                    "id": tc.id,
                    "node_id": tc.node_id,
                    "file_path": tc.file_path,
                    "created_at": _iso(tc.created_at),
                }
                for tc in test_cases
            ],
            "runs": [
                {
                    "id": run.id,
                    "commit_sha": run.commit_sha,
                    "branch": run.branch,
                    "source": run.source.value,
                    "started_at": _iso(run.started_at),
                    "finished_at": _iso(run.finished_at),
                    "created_at": _iso(run.created_at),
                    "coverage_data": run.coverage_data,
                    "results": [
                        {
                            "test_case_id": r.test_case_id,
                            "node_id": r.test_case.node_id,
                            "status": r.status.value,
                            "duration_seconds": r.duration_seconds,
                            "message": r.message,
                        }
                        for r in db.scalars(
                            select(TestResult)
                            .where(TestResult.test_run_id == run.id)
                            .order_by(TestResult.id)
                        ).all()
                    ],
                }
                for run in runs
            ],
        })

    db.close()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "repos": repos_out,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("EXPORT_DATABASE_URL"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("Provide --database-url or set EXPORT_DATABASE_URL")

    data = export(args.database_url)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    total_runs = sum(len(r["runs"]) for r in data["repos"])
    total_results = sum(len(run["results"]) for r in data["repos"] for run in r["runs"])
    print(f"Exported {len(data['repos'])} repo(s), {total_runs} run(s), {total_results} result(s) -> {out_path}")


if __name__ == "__main__":
    main()
