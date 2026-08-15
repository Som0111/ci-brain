from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import RunSource, TestStatus


class RepoCreate(BaseModel):
    name: str
    url: str | None = None


class RepoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str | None
    created_at: datetime


class TestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: str
    file_path: str


class TestResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_case: TestCaseOut
    status: TestStatus
    duration_seconds: float | None
    message: str | None


class TestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repo_id: int
    commit_sha: str | None
    branch: str | None
    source: RunSource
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class TestRunDetailOut(TestRunOut):
    results: list[TestResultOut]


class IngestResult(BaseModel):
    run_id: int
    tests_recorded: int
    passed: int
    failed: int
    skipped: int
    error: int
