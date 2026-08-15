"""Computes pass/fail variance per test across identical-commit runs.

This module only measures variance. Classifying which variance level counts
as "flaky" for a given dataset size is a separate design decision (Phase 3's
threshold step) - see the roadmap's escalation checkpoint for that phase.
"""
from dataclasses import dataclass

from sqlalchemy import select
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
    query = (
        select(TestCase, TestResult.status)
        .join(TestResult, TestResult.test_case_id == TestCase.id)
        .join(TestRun, TestRun.id == TestResult.test_run_id)
        .where(TestCase.repo_id == repo_id)
    )
    if commit_sha is not None:
        query = query.where(TestRun.commit_sha == commit_sha)

    by_test: dict[int, TestVarianceStats] = {}
    for test_case, status in db.execute(query).all():
        stats = by_test.setdefault(
            test_case.id, TestVarianceStats(node_id=test_case.node_id, file_path=test_case.file_path)
        )
        if status == TestStatus.PASSED:
            stats.pass_count += 1
        elif status == TestStatus.SKIPPED:
            stats.skip_count += 1
        else:  # FAILED or ERROR
            stats.fail_count += 1

    return sorted(by_test.values(), key=lambda s: s.node_id)
