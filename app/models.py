import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TestStatus(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class RunSource(str, enum.Enum):
    JUNIT = "junit"
    COVERAGE = "coverage"


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    runs: Mapped[list["TestRun"]] = relationship(back_populates="repo", cascade="all, delete-orphan")
    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="repo", cascade="all, delete-orphan")


class TestCase(Base):
    """A distinct test identified by its pytest node id, unique per repo."""

    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("repo_id", "node_id", name="uq_test_case_repo_node"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(1000))
    file_path: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    repo: Mapped["Repo"] = relationship(back_populates="test_cases")
    results: Mapped[list["TestResult"]] = relationship(back_populates="test_case", cascade="all, delete-orphan")


class TestRun(Base):
    """One execution of the target repo's test suite (one replay-harness pass)."""

    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[RunSource] = mapped_column(
        Enum(RunSource, name="run_source", values_callable=lambda e: [m.value for m in e])
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Raw coverage.py JSON (file -> executed lines / summary) for this run, when supplied.
    coverage_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    repo: Mapped["Repo"] = relationship(back_populates="runs")
    results: Mapped[list["TestResult"]] = relationship(back_populates="test_run", cascade="all, delete-orphan")


class TestResult(Base):
    """The outcome of one test case within one test run."""

    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), index=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"), index=True)
    status: Mapped[TestStatus] = mapped_column(
        Enum(TestStatus, name="test_status", values_callable=lambda e: [m.value for m in e])
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    test_run: Mapped["TestRun"] = relationship(back_populates="results")
    test_case: Mapped["TestCase"] = relationship(back_populates="results")
