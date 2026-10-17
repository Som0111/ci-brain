from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.clustering import cluster_failures, fetch_failures
from app.analysis.impact import build_dependency_graph
from app.analysis.summarize import SummarizerError, summarize_cluster
from app.database import get_db
from app.models import Repo, TestCase, TestRun
from app.security import require_api_key

router = APIRouter(
    tags=["clusters"],
    responses={
        404: {"description": "Repo, run or baseline repo not found"},
        400: {"description": "baseline_repo_id shares no test ids with this repo"},
    },
)

GROUPING_NOTE = (
    "Clusters are heuristic groupings (identical set of source files the failing test is known to cover, plus the "
    "function pytest named in the assertion, if any). They are NOT confirmed root causes: independent bugs in the "
    "same file can share a cluster, and one bug can split across clusters."
)
MAX_MESSAGE_CHARS = 2000  # representative_message is truncated in responses


class ClusterEntry(BaseModel):
    size: int = Field(description="Number of failure records (a test failing in N runs counts N times)")
    distinct_tests: int = Field(description="Number of distinct failing tests in the cluster")
    has_coverage: bool = Field(description="False when no coverage known for these tests (hint-only grouping)")
    covered_files: list[str] = Field(description="OBSERVED: source files the failing tests are known to execute")
    call_hint: str | None = Field(description="OBSERVED: function named by pytest's assertion rewrite, if present")
    tests: list[str]
    representative_message: str = Field(description="OBSERVED: shortest failure message, truncated to 2000 chars")


class ClusterReport(BaseModel):
    repo_id: int
    total_failures: int
    note: str = GROUPING_NOTE
    clusters: list[ClusterEntry]


def _entry_fields(c) -> dict:
    tests = sorted({f.node_id for f in c.failures})
    return dict(
        size=c.size,
        distinct_tests=len(tests),
        has_coverage=bool(c.covered_files),
        covered_files=sorted(c.covered_files),
        call_hint=c.call_hint,
        tests=tests,
        representative_message=c.representative.message[:MAX_MESSAGE_CHARS],
    )


def _test_covered_files(db: Session, repo_id: int) -> dict[str, frozenset[str]]:
    graph = build_dependency_graph(db, repo_id)
    by_test: dict[str, set[str]] = {}
    for file, tests in graph.items():
        for t in tests:
            by_test.setdefault(t, set()).add(file)
    return {k: frozenset(v) for k, v in by_test.items()}


def _validate_scope(db: Session, repo_id: int, run_id: int | None, baseline_repo_id: int | None) -> None:
    """404 for unknown repo/run/baseline; 400 if the baseline shares no test ids with the repo."""
    if db.get(Repo, repo_id) is None:
        raise HTTPException(status_code=404, detail="repo not found")
    if run_id is not None:
        run = db.get(TestRun, run_id)
        if run is None or run.repo_id != repo_id:
            raise HTTPException(status_code=404, detail="run not found for this repo")
    if baseline_repo_id is not None and baseline_repo_id != repo_id:
        if db.get(Repo, baseline_repo_id) is None:
            raise HTTPException(status_code=404, detail="baseline repo not found")
        shared = db.scalar(
            select(TestCase.id)
            .where(
                TestCase.repo_id == repo_id,
                TestCase.node_id.in_(select(TestCase.node_id).where(TestCase.repo_id == baseline_repo_id)),
            )
            .limit(1)
        )
        if shared is None:
            raise HTTPException(status_code=400, detail="baseline repo shares no test ids with this repo")


@router.get("/repos/{repo_id}/failure-clusters", response_model=ClusterReport)
def failure_clusters(
    repo_id: int,
    run_id: int | None = Query(None, ge=1),
    baseline_repo_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    """`baseline_repo_id` points the dependency graph at a different repo's
    coverage data - useful when `repo_id` is a seeded variant (e.g. this
    project's `toolz-bug-seed`) that shares the same codebase and test ids as
    a clean baseline (`toolz`) but whose *own* coverage, recorded under
    active bugs, isn't the reference we want for attributing root cause.
    Defaults to `repo_id` itself when omitted."""
    _validate_scope(db, repo_id, run_id, baseline_repo_id)

    failures = fetch_failures(db, repo_id, run_id)
    covered = _test_covered_files(db, baseline_repo_id if baseline_repo_id is not None else repo_id)
    clusters = cluster_failures(failures, covered)

    return ClusterReport(
        repo_id=repo_id,
        total_failures=len(failures),
        clusters=[
            ClusterEntry(**_entry_fields(c))
            for c in clusters
        ],
    )


class SummarizedClusterEntry(ClusterEntry):
    hypothesis: str | None = Field(
        description="MODEL-GENERATED guess (Gemini) from the observed fields above; unverified, may be wrong"
    )
    llm_error: str | None = None


class SummarizedClusterReport(BaseModel):
    repo_id: int
    total_failures: int
    clusters_summarized: int
    clusters_skipped: int
    note: str = GROUPING_NOTE + " 'hypothesis' fields are model-generated text, not observed evidence."
    clusters: list[SummarizedClusterEntry]


@router.post(
    "/repos/{repo_id}/failure-clusters/summarize",
    response_model=SummarizedClusterReport,
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing or invalid X-API-Key (only when API_KEY is configured)"}},
)
def summarize_failure_clusters(
    repo_id: int,
    run_id: int | None = Query(None, ge=1),
    baseline_repo_id: int | None = Query(None, ge=1),
    min_cluster_size: int = Query(2, ge=1, le=1000),
    max_clusters: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Costs one real LLM API call per summarized cluster - deliberately a
    POST with cost-bounding params (min_cluster_size, max_clusters), never
    triggered implicitly by the free GET report above."""
    _validate_scope(db, repo_id, run_id, baseline_repo_id)

    failures = fetch_failures(db, repo_id, run_id)
    covered = _test_covered_files(db, baseline_repo_id if baseline_repo_id is not None else repo_id)
    clusters = cluster_failures(failures, covered)

    eligible = [c for c in clusters if c.size >= min_cluster_size][:max_clusters]
    skipped = len(clusters) - len(eligible)

    entries = []
    for c in eligible:
        hypothesis, error = None, None
        if not c.representative.message.strip():
            error = "no failure message recorded for this cluster; nothing for the model to analyze"
        else:
            try:
                hypothesis = summarize_cluster(c).hypothesis
            except SummarizerError as exc:
                error = str(exc)
        entries.append(SummarizedClusterEntry(**_entry_fields(c), hypothesis=hypothesis, llm_error=error))

    return SummarizedClusterReport(
        repo_id=repo_id,
        total_failures=len(failures),
        clusters_summarized=len(entries),
        clusters_skipped=skipped,
        clusters=entries,
    )
