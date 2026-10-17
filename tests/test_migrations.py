# ruff: noqa: E501
"""Alembic migration checks.

Always runs against SQLite; the same checks run against PostgreSQL when
TEST_POSTGRES_URL is set (e.g. postgresql+psycopg2://ci_brain:ci_brain@localhost:5432/ci_brain_test).
The Postgres database is WIPED (public schema dropped) by these tests - point it at a throwaway DB.
"""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.config import settings
from app.database import Base

PG_URL = os.environ.get("TEST_POSTGRES_URL")


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(not PG_URL, reason="TEST_POSTGRES_URL not set"))])
def db_url(request, tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}" if request.param == "sqlite" else PG_URL
    if request.param == "postgres":
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
        eng.dispose()
    monkeypatch.setattr(settings, "database_url", url)  # alembic/env.py reads this
    return url


def _cfg():
    return Config("alembic.ini")


def _seed(conn, duration):
    conn.execute(text("INSERT INTO repos (id, name, created_at) VALUES (1, 'r', '2026-01-01')"))
    conn.execute(text("INSERT INTO test_cases (id, repo_id, node_id, file_path, created_at) VALUES (1, 1, 'a::t', 'a.py', '2026-01-01')"))
    conn.execute(text("INSERT INTO test_runs (id, repo_id, source, created_at) VALUES (1, 1, 'junit', '2026-01-01')"))
    conn.execute(
        text(
            "INSERT INTO test_results (id, test_run_id, test_case_id, status, duration_seconds, created_at) "
            "VALUES (1, 1, 1, 'passed', :d, '2026-01-01')"
        ),
        {"d": duration},
    )


def test_fresh_upgrade_matches_models_and_downgrades_cleanly(db_url):
    command.upgrade(_cfg(), "head")
    eng = create_engine(db_url)
    try:
        diff = compare_metadata(MigrationContext.configure(eng.connect()), Base.metadata)
        assert diff == [], f"models and migrations have drifted: {diff}"
        assert {"repos", "test_cases", "test_runs", "test_results"} <= set(inspect(eng).get_table_names())
    finally:
        eng.dispose()
    command.downgrade(_cfg(), "base")
    eng = create_engine(db_url)
    assert set(inspect(eng).get_table_names()) <= {"alembic_version"}
    eng.dispose()


def test_upgrade_from_prior_schema_keeps_data_and_cleans_negative_durations(db_url):
    command.upgrade(_cfg(), "0001")
    eng = create_engine(db_url)
    with eng.begin() as c:
        _seed(c, -5.0)  # impossible via the API, possible in old data
    command.upgrade(_cfg(), "head")
    with eng.connect() as c:
        assert c.execute(text("SELECT duration_seconds FROM test_results")).scalar() is None
        assert c.execute(text("SELECT count(*) FROM test_results")).scalar() == 1
    eng.dispose()


def test_check_constraint_and_unique_constraint_enforced(db_url):
    command.upgrade(_cfg(), "head")
    eng = create_engine(db_url)
    with eng.begin() as c:
        _seed(c, 0.5)
    with pytest.raises(IntegrityError), eng.begin() as c:
        c.execute(text("UPDATE test_results SET duration_seconds = -1"))
    with pytest.raises(IntegrityError), eng.begin() as c:  # duplicate (repo_id, node_id)
        c.execute(text("INSERT INTO test_cases (id, repo_id, node_id, file_path, created_at) VALUES (2, 1, 'a::t', 'a.py', '2026-01-01')"))
    eng.dispose()


def test_orm_roundtrip_enum_json_and_cascade_delete(db_url):
    """Enum values, JSON column and repo deletion through the ORM on the migrated schema."""
    from sqlalchemy.orm import Session

    from app.models import Repo, RunSource, TestCase, TestResult, TestRun, TestStatus

    command.upgrade(_cfg(), "head")
    eng = create_engine(db_url)
    with Session(eng) as s:
        repo = Repo(name="r")
        case = TestCase(repo=repo, node_id="a::t", file_path="a.py")
        run = TestRun(repo=repo, source=RunSource.JUNIT, coverage_data={"files": {"a.py": {"contexts": {"1": ["x"]}}}})
        s.add_all([repo, case, run, TestResult(test_run=run, test_case=case, status=TestStatus.FAILED, duration_seconds=1.5)])
        s.commit()
        rid = repo.id
    with Session(eng) as s:
        assert s.get(TestRun, 1).coverage_data["files"]["a.py"]["contexts"]["1"] == ["x"]
        assert s.query(TestResult).filter(TestResult.status == TestStatus.FAILED).count() == 1
        s.delete(s.get(Repo, rid))
        s.commit()
        assert [s.query(m).count() for m in (TestCase, TestRun, TestResult)] == [0, 0, 0]
    eng.dispose()
