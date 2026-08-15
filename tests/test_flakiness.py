import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.flakiness import compute_variance_stats
from app.database import Base
from app.models import Repo, RunSource
from app.models import TestCase as TestCaseModel
from app.models import TestResult as TestResultModel
from app.models import TestRun as TestRunModel
from app.models import TestStatus


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_run(db: Session, repo_id: int, commit_sha: str, statuses: dict[str, TestStatus]) -> None:
    run = TestRunModel(repo_id=repo_id, commit_sha=commit_sha, source=RunSource.JUNIT)
    db.add(run)
    db.flush()
    for node_id, status in statuses.items():
        tc = db.query(TestCaseModel).filter_by(repo_id=repo_id, node_id=node_id).first()
        if tc is None:
            tc = TestCaseModel(repo_id=repo_id, node_id=node_id, file_path=f"{node_id}.py")
            db.add(tc)
            db.flush()
        db.add(TestResultModel(test_run_id=run.id, test_case_id=tc.id, status=status))
    db.commit()


def test_stable_test_has_zero_fail_rate(db):
    repo = Repo(name="r", url=None)
    db.add(repo)
    db.commit()

    for _ in range(5):
        _seed_run(db, repo.id, "abc123", {"test_stable": TestStatus.PASSED})

    stats = compute_variance_stats(db, repo.id)
    assert len(stats) == 1
    assert stats[0].node_id == "test_stable"
    assert stats[0].pass_count == 5
    assert stats[0].fail_count == 0
    assert stats[0].fail_rate == 0.0
    assert stats[0].is_inconsistent is False


def test_flaky_test_shows_inconsistent_results(db):
    repo = Repo(name="r", url=None)
    db.add(repo)
    db.commit()

    outcomes = [TestStatus.PASSED, TestStatus.FAILED, TestStatus.PASSED, TestStatus.PASSED, TestStatus.FAILED]
    for outcome in outcomes:
        _seed_run(db, repo.id, "abc123", {"test_flaky": outcome})

    stats = compute_variance_stats(db, repo.id)
    assert stats[0].pass_count == 3
    assert stats[0].fail_count == 2
    assert stats[0].fail_rate == pytest.approx(0.4)
    assert stats[0].is_inconsistent is True


def test_skips_dont_count_as_pass_or_fail(db):
    repo = Repo(name="r", url=None)
    db.add(repo)
    db.commit()

    _seed_run(db, repo.id, "abc123", {"test_skipped": TestStatus.SKIPPED})
    _seed_run(db, repo.id, "abc123", {"test_skipped": TestStatus.SKIPPED})

    stats = compute_variance_stats(db, repo.id)
    assert stats[0].skip_count == 2
    assert stats[0].non_skip_runs == 0
    assert stats[0].fail_rate == 0.0  # no divide-by-zero
    assert stats[0].is_inconsistent is False


def test_commit_sha_filter_isolates_runs(db):
    repo = Repo(name="r", url=None)
    db.add(repo)
    db.commit()

    _seed_run(db, repo.id, "commit_a", {"test_x": TestStatus.PASSED})
    _seed_run(db, repo.id, "commit_b", {"test_x": TestStatus.FAILED})

    stats_a = compute_variance_stats(db, repo.id, commit_sha="commit_a")
    assert stats_a[0].pass_count == 1
    assert stats_a[0].fail_count == 0

    stats_all = compute_variance_stats(db, repo.id)
    assert stats_all[0].pass_count == 1
    assert stats_all[0].fail_count == 1
