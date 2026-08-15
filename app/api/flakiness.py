from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analysis.classify import classify_all
from app.analysis.flakiness import compute_variance_stats
from app.database import get_db
from app.models import Repo

router = APIRouter(tags=["flakiness"])


class FlakinessEntry(BaseModel):
    node_id: str
    file_path: str
    verdict: str
    confidence: str | None
    quarantine: bool
    pass_count: int
    fail_count: int
    skip_count: int
    fail_rate: float


class FlakinessReport(BaseModel):
    repo_id: int
    commit_sha: str | None
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
        total_tests=len(classified),
        flaky=[entry(c) for c in classified if c.verdict.value == "flaky"],
        consistently_failing=[entry(c) for c in classified if c.verdict.value == "consistently_failing"],
        insufficient_data=[entry(c) for c in classified if c.verdict.value == "insufficient_data"],
        stable_count=sum(1 for c in classified if c.verdict.value == "stable"),
    )
