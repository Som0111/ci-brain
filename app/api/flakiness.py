from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.analysis.classify import classify_all
from app.analysis.flakiness import compute_variance_stats
from app.database import get_db
from app.models import Repo, RunSource, TestRun

router = APIRouter(tags=["flakiness"], responses={404: {"description": "Repo (or run) not found"}})


class FlakinessEntry(BaseModel):
    node_id: str
    file_path: str
    verdict: str
    confidence: str | None = Field(
        description="Evidence-strength label for FLAKY only, from how often the rarer outcome was seen "
        "(>=3 high, 2 medium, 1 low). A heuristic label, NOT a statistical probability."
    )
    quarantine: bool = Field(description="Recommendation: flaky with high or medium confidence")
    pass_count: int
    fail_count: int
    skip_count: int
    fail_rate: float


class FlakinessReport(BaseModel):
    repo_id: int
    commit_sha: str | None
    commits_seen: int = Field(description="Distinct commit_sha values among the runs analysed")
    warning: str | None = Field(
        None,
        description="Set when unscoped results mix commits (or runs with no commit): a pass/fail change across "
        "different code revisions is not evidence of flakiness. Pass commit_sha to scope.",
    )
    total_tests: int
    flaky: list[FlakinessEntry]
    consistently_failing: list[FlakinessEntry]
    insufficient_data: list[FlakinessEntry]
    stable_count: int


@router.get("/repos/{repo_id}/flakiness", response_model=FlakinessReport)
def flakiness_report(repo_id: int, commit_sha: str | None = None, db: Session = Depends(get_db)):
    if db.get(Repo, repo_id) is None:
        raise HTTPException(status_code=404, detail="repo not found")

    stats = compute_variance_stats(db, repo_id, commit_sha=commit_sha)

    commits_seen, warning = (1 if commit_sha else 0), None
    if commit_sha is None:
        junit_runs = select(TestRun).where(TestRun.repo_id == repo_id, TestRun.source == RunSource.JUNIT)
        commits_seen = db.scalar(select(func.count(distinct(junit_runs.subquery().c.commit_sha)))) or 0
        no_commit_runs = junit_runs.where(TestRun.commit_sha.is_(None)).subquery()
        no_commit = db.scalar(select(func.count()).select_from(no_commit_runs))
        if commits_seen + (1 if no_commit else 0) > 1:
            warning = (
                f"results pool {commits_seen} commit(s)"
                + (f" plus {no_commit} run(s) without a commit_sha" if no_commit else "")
                + "; variance across different code revisions is not necessarily flakiness - "
                "pass commit_sha to scope the report"
            )
    classified = classify_all(stats)

    def entry(c) -> FlakinessEntry:
        return FlakinessEntry(
            node_id=c.stats.node_id,
            file_path=c.stats.file_path,
            verdict=c.verdict.value,
            confidence=c.confidence.value if c.confidence else None,
            quarantine=c.quarantine,
            pass_count=c.stats.pass_count,
            fail_count=c.stats.fail_count,
            skip_count=c.stats.skip_count,
            fail_rate=round(c.stats.fail_rate, 4),
        )

    return FlakinessReport(
        repo_id=repo_id,
        commit_sha=commit_sha,
        commits_seen=commits_seen,
        warning=warning,
        total_tests=len(classified),
        flaky=[entry(c) for c in classified if c.verdict.value == "flaky"],
        consistently_failing=[entry(c) for c in classified if c.verdict.value == "consistently_failing"],
        insufficient_data=[entry(c) for c in classified if c.verdict.value == "insufficient_data"],
        stable_count=sum(1 for c in classified if c.verdict.value == "stable"),
    )
