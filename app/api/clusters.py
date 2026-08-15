from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analysis.clustering import cluster_failures, fetch_failures
from app.analysis.impact import build_dependency_graph
from app.analysis.summarize import SummarizerNotConfigured, summarize_cluster
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


class SummarizedClusterEntry(ClusterEntry):
    hypothesis: str | None
    llm_error: str | None = None


class SummarizedClusterReport(BaseModel):
    repo_id: int
    total_failures: int
    clusters_summarized: int
    clusters_skipped: int
    clusters: list[SummarizedClusterEntry]


@router.post("/repos/{repo_id}/failure-clusters/summarize", response_model=SummarizedClusterReport)
def summarize_failure_clusters(
    repo_id: int,
    run_id: int | None = None,
    baseline_repo_id: int | None = None,
    min_cluster_size: int = 2,
    max_clusters: int = 10,
    db: Session = Depends(get_db),
):
    """Costs one real LLM API call per summarized cluster - deliberately a
    POST with cost-bounding params (min_cluster_size, max_clusters), never
    triggered implicitly by the free GET report above."""
    if db.get(Repo, repo_id) is None:
        raise HTTPException(status_code=404, detail="repo not found")

    failures = fetch_failures(db, repo_id, run_id)
    covered = _test_covered_files(db, baseline_repo_id if baseline_repo_id is not None else repo_id)
    clusters = cluster_failures(failures, covered)

    eligible = [c for c in clusters if c.size >= min_cluster_size][:max_clusters]
    skipped = len(clusters) - len(eligible)

    entries = []
    for c in eligible:
        hypothesis, error = None, None
        try:
            hypothesis = summarize_cluster(c).hypothesis
        except SummarizerNotConfigured as exc:
            error = str(exc)
        entries.append(
            SummarizedClusterEntry(
                size=c.size,
                covered_files=sorted(c.covered_files),
                call_hint=c.call_hint,
                tests=sorted({f.node_id for f in c.failures}),
                representative_message=c.representative.message,
                hypothesis=hypothesis,
                llm_error=error,
            )
        )

    return SummarizedClusterReport(
        repo_id=repo_id,
        total_failures=len(failures),
        clusters_summarized=len(entries),
        clusters_skipped=skipped,
        clusters=entries,
    )
