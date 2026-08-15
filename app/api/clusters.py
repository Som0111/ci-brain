from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analysis.clustering import cluster_failures, fetch_failures
from app.analysis.impact import build_dependency_graph
from app.database import get_db
from app.models import Repo

router = APIRouter(tags=["clusters"])


class ClusterEntry(BaseModel):
    size: int
    covered_files: list[str]
    call_hint: str | None
    tests: list[str]
    representative_message: str


class ClusterReport(BaseModel):
    repo_id: int
    total_failures: int
    clusters: list[ClusterEntry]


def _test_covered_files(db: Session, repo_id: int) -> dict[str, frozenset[str]]:
    graph = build_dependency_graph(db, repo_id)
    by_test: dict[str, set[str]] = {}
    for file, tests in graph.items():
        for t in tests:
            by_test.setdefault(t, set()).add(file)
    return {k: frozenset(v) for k, v in by_test.items()}


@router.get("/repos/{repo_id}/failure-clusters", response_model=ClusterReport)
def failure_clusters(
    repo_id: int, run_id: int | None = None, baseline_repo_id: int | None = None, db: Session = Depends(get_db)
):
    """`baseline_repo_id` points the dependency graph at a different repo's
    coverage data - useful when `repo_id` is a seeded variant (e.g. this
    project's `toolz-bug-seed`) that shares the same codebase and test ids as
    a clean baseline (`toolz`) but whose *own* coverage, recorded under
    active bugs, isn't the reference we want for attributing root cause.
    Defaults to `repo_id` itself when omitted."""
    if db.get(Repo, repo_id) is None:
        raise HTTPException(status_code=404, detail="repo not found")

    failures = fetch_failures(db, repo_id, run_id)
    covered = _test_covered_files(db, baseline_repo_id if baseline_repo_id is not None else repo_id)
    clusters = cluster_failures(failures, covered)

    return ClusterReport(
        repo_id=repo_id,
        total_failures=len(failures),
        clusters=[
            ClusterEntry(
                size=c.size,
                covered_files=sorted(c.covered_files),
                call_hint=c.call_hint,
                tests=sorted({f.node_id for f in c.failures}),
                representative_message=c.representative.message,
            )
            for c in clusters
        ],
    )
