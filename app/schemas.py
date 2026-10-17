from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.models import RunSource, TestStatus


class RepoCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None

    @field_validator("url")
    @classmethod
    def _blank_url_is_none(cls, v):
        return v or None


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
    duplicate: bool = False  # True when run_key matched an already-ingested run (nothing new stored)
    tests_recorded: int
    passed: int
    failed: int
    skipped: int
    error: int
