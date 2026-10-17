"""Computes pass/fail variance per test across identical-commit runs.

This module only measures variance. Classifying which variance level counts
as "flaky" for a given dataset size is a separate design decision (Phase 3's
threshold step) - see the roadmap's escalation checkpoint for that phase.
"""
from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import TestCase, TestResult, TestRun, TestStatus


@dataclass
class TestVarianceStats:
    node_id: str
    file_path: str
    pass_count: int = 0
    fail_count: int = 0  # 'failed' or 'error'
    skip_count: int = 0

    @property
    def total_runs(self) -> int:
        return self.pass_count + self.fail_count + self.skip_count

    @property
    def non_skip_runs(self) -> int:
        return self.pass_count + self.fail_count

    @property
    def fail_rate(self) -> float:
        return self.fail_count / self.non_skip_runs if self.non_skip_runs else 0.0

    @property
    def is_inconsistent(self) -> bool:
        """True if this test produced both a pass and a fail across the observed
        runs - the raw signal a flakiness threshold gets applied to."""
        return self.pass_count > 0 and self.fail_count > 0


def compute_variance_stats(
    db: Session, repo_id: int, commit_sha: str | None = None
) -> list[TestVarianceStats]:
    """One row per distinct test in `repo_id`, tallying pass/fail/skip counts
    across all stored runs (optionally restricted to one commit, since
    variance is only meaningful across *identical-commit* runs - a real code
    change is expected to change results)."""
    # Aggregate in SQL: one row per test, instead of one Python object per stored result.
    passed = func.sum(case((TestResult.status == TestStatus.PASSED, 1), else_=0))
    skipped = func.sum(case((TestResult.status == TestStatus.SKIPPED, 1), else_=0))
    total = func.count(TestResult.id)
    query = (
        select(TestCase.node_id, TestCase.file_path, passed, skipped, total)
        .join(TestResult, TestResult.test_case_id == TestCase.id)
        .join(TestRun, TestRun.id == TestResult.test_run_id)
        .where(TestCase.repo_id == repo_id)
        .group_by(TestCase.id, TestCase.node_id, TestCase.file_path)
        .order_by(TestCase.node_id)
    )
    if commit_sha is not None:
        query = query.where(TestRun.commit_sha == commit_sha)

    stats = []
    for node_id, file_path, n_pass, n_skip, n_total in db.execute(query):
        n_pass, n_skip = int(n_pass or 0), int(n_skip or 0)
        # anything that is neither passed nor skipped (FAILED / ERROR) is a fail
        stats.append(
            TestVarianceStats(
                node_id=node_id,
                file_path=file_path,
                pass_count=n_pass,
                fail_count=n_total - n_pass - n_skip,
                skip_count=n_skip,
            )
        )
    return stats
