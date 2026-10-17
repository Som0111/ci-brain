import logging
import re

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_db
from app.logging_config import want_traceback
from app.models import Repo, RunSource, TestCase, TestResult, TestRun, TestStatus
from app.parsers.coverage_json import CoverageParseError, parse_coverage_json
from app.parsers.junit import JUnitParseError, parse_junit_xml
from app.schemas import IngestResult, TestCaseOut, TestRunDetailOut, TestRunOut
from app.security import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(tags=["runs"], responses={404: {"description": "Repo (or run) not found"}})

_SHA_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean_metadata(
    commit_sha: str | None, branch: str | None, run_key: str | None
) -> tuple[str | None, str | None, str | None]:
    commit_sha = (commit_sha or "").strip() or None
    branch = (branch or "").strip() or None
    run_key = (run_key or "").strip() or None
    if run_key and (len(run_key) > 128 or _CONTROL_RE.search(run_key)):
        raise HTTPException(status_code=400, detail="run_key must be at most 128 chars with no control characters")
    if commit_sha and not _SHA_RE.match(commit_sha):
        raise HTTPException(status_code=400, detail="commit_sha must be 1-40 chars of [A-Za-z0-9._-]")
    if branch and (len(branch) > 255 or _CONTROL_RE.search(branch)):
        raise HTTPException(status_code=400, detail="branch must be at most 255 chars with no control characters")
    return commit_sha, branch, run_key


async def _read_limited(upload: UploadFile, field: str) -> bytes:
    """Read at most max_upload_bytes; never buffers an oversized body in full."""
    limit = settings.max_upload_bytes
    raw = await upload.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail=f"{field} exceeds {limit} bytes")
    return raw


def _get_repo_or_404(repo_id: int, db: Session) -> Repo:
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return repo


def _existing_run_result(db: Session, repo_id: int, run_key: str | None) -> IngestResult | None:
    """If a run with this (repo, run_key) was already ingested, describe it (CI retry -> same answer)."""
    if not run_key:
        return None
    run = db.scalar(select(TestRun).where(TestRun.repo_id == repo_id, TestRun.run_key == run_key))
    if run is None:
        return None
    by_status = dict(
        db.execute(
            select(TestResult.status, func.count()).where(TestResult.test_run_id == run.id).group_by(TestResult.status)
        ).all()
    )
    count = {s.value: by_status.get(s, 0) for s in TestStatus}
    return IngestResult(
        run_id=run.id, tests_recorded=sum(count.values()), duplicate=True,
        passed=count["passed"], failed=count["failed"], skipped=count["skipped"], error=count["error"],
    )


def _get_or_create_test_case(db: Session, repo_id: int, node_id: str, file_path: str) -> TestCase:
    tc = db.scalar(
        select(TestCase).where(TestCase.repo_id == repo_id, TestCase.node_id == node_id)
    )
    if tc is None:
        try:
            with db.begin_nested():  # savepoint: a lost race must not poison the outer transaction
                tc = TestCase(repo_id=repo_id, node_id=node_id, file_path=file_path)
                db.add(tc)
        except IntegrityError:
            tc = db.scalar(
                select(TestCase).where(TestCase.repo_id == repo_id, TestCase.node_id == node_id)
            )
    return tc


@router.post(
    "/repos/{repo_id}/runs",
    response_model=IngestResult,
    status_code=201,
    dependencies=[Depends(require_api_key)],
    responses={
        200: {"description": "run_key already ingested for this repo; returns the original run (duplicate=true)"},
        400: {"description": "Invalid or missing upload / metadata"},
        401: {"description": "Missing or invalid X-API-Key (only when API_KEY is configured)"},
        404: {"description": "Repo not found"},
        413: {"description": "Upload exceeds MAX_UPLOAD_BYTES"},
        503: {"description": "Database error; nothing stored"},
    },
)
async def ingest_run(
    repo_id: int,
    junit_xml: UploadFile | None = None,
    coverage_json: UploadFile | None = None,
    commit_sha: str | None = Form(None),
    branch: str | None = Form(None),
    run_key: str | None = Form(None, description="Optional idempotency key (e.g. CI run id + attempt)"),
    response: Response = None,
    db: Session = Depends(get_db),
):
    _get_repo_or_404(repo_id, db)

    if junit_xml is None and coverage_json is None:
        raise HTTPException(status_code=400, detail="upload at least one of junit_xml or coverage_json")
    commit_sha, branch, run_key = _clean_metadata(commit_sha, branch, run_key)

    # A CI retry that re-sends the same run must not count as independent evidence of flakiness.
    duplicate = _existing_run_result(db, repo_id, run_key)
    if duplicate is not None:
        response.status_code = 200
        return duplicate

    coverage_data = None
    if coverage_json is not None:
        raw = await _read_limited(coverage_json, "coverage_json")
        try:
            coverage_data = parse_coverage_json(raw)
        except CoverageParseError as exc:
            raise HTTPException(status_code=400, detail=f"coverage_json: {exc}") from exc

    if junit_xml is None:
        run = TestRun(
            repo_id=repo_id,
            commit_sha=commit_sha,
            branch=branch,
            run_key=run_key,
            source=RunSource.COVERAGE,
            coverage_data=coverage_data,
        )
        try:
            db.add(run)
            db.commit()
            db.refresh(run)
        except SQLAlchemyError as exc:
            db.rollback()
            raced = _existing_run_result(db, repo_id, run_key) if isinstance(exc, IntegrityError) else None
            if raced is not None:  # concurrent request with the same run_key won
                response.status_code = 200
                return raced
            logger.error(
                "coverage ingestion failed for repo %s: %s", repo_id, type(exc).__name__, exc_info=want_traceback()
            )
            raise HTTPException(status_code=503, detail="database error; nothing was stored") from exc
        return IngestResult(run_id=run.id, tests_recorded=0, passed=0, failed=0, skipped=0, error=0)

    raw = await _read_limited(junit_xml, "junit_xml")
    try:
        parsed = parse_junit_xml(raw)
    except JUnitParseError as exc:
        raise HTTPException(status_code=400, detail=f"junit_xml: {exc}") from exc

    if len(parsed) > settings.max_results_per_run:
        raise HTTPException(status_code=413, detail=f"junit_xml has more than {settings.max_results_per_run} results")

    try:
        return _store_junit_run(db, repo_id, commit_sha, branch, run_key, coverage_data, parsed)
    except SQLAlchemyError as exc:
        db.rollback()
        raced = _existing_run_result(db, repo_id, run_key) if isinstance(exc, IntegrityError) else None
        if raced is not None:  # concurrent request with the same run_key won
            response.status_code = 200
            return raced
        logger.error("ingestion failed for repo %s: %s", repo_id, type(exc).__name__, exc_info=want_traceback())
        raise HTTPException(status_code=503, detail="database error; nothing was stored") from exc


def _store_junit_run(db, repo_id, commit_sha, branch, run_key, coverage_data, parsed) -> IngestResult:
    run = TestRun(
        repo_id=repo_id,
        commit_sha=commit_sha,
        branch=branch,
        run_key=run_key,
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
    logger.info("ingested run %s for repo %s: %d results", run.id, repo_id, len(parsed))

    return IngestResult(
        run_id=run.id,
        tests_recorded=len(parsed),
        passed=counts["passed"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        error=counts["error"],
    )


DEFAULT_PAGE = 500
MAX_PAGE = 1000


@router.get("/repos/{repo_id}/runs", response_model=list[TestRunOut])
def list_runs(
    repo_id: int,
    response: Response,
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Newest first. `X-Total-Count` header = total runs, so callers can tell when the list was truncated."""
    _get_repo_or_404(repo_id, db)
    response.headers["X-Total-Count"] = str(
        db.scalar(select(func.count()).select_from(TestRun).where(TestRun.repo_id == repo_id))
    )
    return db.scalars(
        select(TestRun).where(TestRun.repo_id == repo_id).order_by(TestRun.id.desc()).limit(limit).offset(offset)
    ).all()


@router.get("/repos/{repo_id}/tests", response_model=list[TestCaseOut])
def list_tests(
    repo_id: int,
    response: Response,
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Ordered by node_id. `X-Total-Count` header = total tests."""
    _get_repo_or_404(repo_id, db)
    response.headers["X-Total-Count"] = str(
        db.scalar(select(func.count()).select_from(TestCase).where(TestCase.repo_id == repo_id))
    )
    return db.scalars(
        select(TestCase).where(TestCase.repo_id == repo_id).order_by(TestCase.node_id).limit(limit).offset(offset)
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
