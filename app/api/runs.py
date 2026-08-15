from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Repo, RunSource, TestCase, TestResult, TestRun, TestStatus
from app.parsers.coverage_json import CoverageParseError, parse_coverage_json
from app.parsers.junit import JUnitParseError, parse_junit_xml
from app.schemas import IngestResult, TestCaseOut, TestRunDetailOut, TestRunOut

router = APIRouter(tags=["runs"])


def _get_repo_or_404(repo_id: int, db: Session) -> Repo:
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return repo


def _get_or_create_test_case(db: Session, repo_id: int, node_id: str, file_path: str) -> TestCase:
    tc = db.scalar(
        select(TestCase).where(TestCase.repo_id == repo_id, TestCase.node_id == node_id)
    )
    if tc is None:
        tc = TestCase(repo_id=repo_id, node_id=node_id, file_path=file_path)
        db.add(tc)
        db.flush()
    return tc


@router.post("/repos/{repo_id}/runs", response_model=IngestResult, status_code=201)
async def ingest_run(
    repo_id: int,
    junit_xml: UploadFile | None = None,
    coverage_json: UploadFile | None = None,
    commit_sha: str | None = Form(None),
    branch: str | None = Form(None),
    db: Session = Depends(get_db),
):
    _get_repo_or_404(repo_id, db)

    if junit_xml is None and coverage_json is None:
        raise HTTPException(status_code=400, detail="upload at least one of junit_xml or coverage_json")

    coverage_data = None
    if coverage_json is not None:
        raw = await coverage_json.read()
        try:
            coverage_data = parse_coverage_json(raw)
        except CoverageParseError as exc:
            raise HTTPException(status_code=400, detail=f"coverage_json: {exc}") from exc

    if junit_xml is None:
        run = TestRun(
            repo_id=repo_id,
            commit_sha=commit_sha,
            branch=branch,
            source=RunSource.COVERAGE,
            coverage_data=coverage_data,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return IngestResult(run_id=run.id, tests_recorded=0, passed=0, failed=0, skipped=0, error=0)

    raw = await junit_xml.read()
    try:
        parsed = parse_junit_xml(raw)
    except JUnitParseError as exc:
        raise HTTPException(status_code=400, detail=f"junit_xml: {exc}") from exc

    run = TestRun(
        repo_id=repo_id,
        commit_sha=commit_sha,
        branch=branch,
        source=RunSource.JUNIT,
        coverage_data=coverage_data,
    )
    db.add(run)
    db.flush()

    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for item in parsed:
        test_case = _get_or_create_test_case(db, repo_id, item.node_id, item.file_path)
        db.add(
            TestResult(
                test_run_id=run.id,
                test_case_id=test_case.id,
                status=TestStatus(item.status),
                duration_seconds=item.duration_seconds,
                message=item.message,
            )
        )
        counts[item.status] += 1

    db.commit()
    db.refresh(run)

    return IngestResult(
        run_id=run.id,
        tests_recorded=len(parsed),
        passed=counts["passed"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        error=counts["error"],
    )


@router.get("/repos/{repo_id}/runs", response_model=list[TestRunOut])
def list_runs(repo_id: int, db: Session = Depends(get_db)):
    _get_repo_or_404(repo_id, db)
    return db.scalars(
        select(TestRun).where(TestRun.repo_id == repo_id).order_by(TestRun.id.desc())
    ).all()


@router.get("/repos/{repo_id}/tests", response_model=list[TestCaseOut])
def list_tests(repo_id: int, db: Session = Depends(get_db)):
    _get_repo_or_404(repo_id, db)
    return db.scalars(
        select(TestCase).where(TestCase.repo_id == repo_id).order_by(TestCase.node_id)
    ).all()


@router.get("/runs/{run_id}", response_model=TestRunDetailOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.scalar(
        select(TestRun)
        .options(selectinload(TestRun.results).selectinload(TestResult.test_case))
        .where(TestRun.id == run_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run
