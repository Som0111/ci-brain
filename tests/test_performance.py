"""P1 item 11: query counts must not grow with history size; lists are paginated; coverage JSON stays deferred."""

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from app.database import get_db
from app.main import app
from app.models import RunSource, TestCase, TestResult, TestRun, TestStatus


def _db():
    return next(app.dependency_overrides[get_db]())


def _seed(repo_id, runs, tests=5):
    db = _db()
    cases = [TestCase(repo_id=repo_id, node_id=f"m::t{i}", file_path="tests/test_m.py") for i in range(tests)]
    db.add_all(cases)
    db.flush()
    cov = {"files": {"pkg/a.py": {"contexts": {"1": [f"tests/test_m.py::t{i}|run" for i in range(tests)]}}}}
    for r in range(runs):
        run = TestRun(repo_id=repo_id, commit_sha="c", source=RunSource.JUNIT, coverage_data=cov)
        db.add(run)
        db.flush()
        db.add_all(
            TestResult(
                test_run_id=run.id,
                test_case_id=c.id,
                status=TestStatus.FAILED if (r + c.id) % 3 == 0 else TestStatus.PASSED,
                message="boom",
            )
            for c in cases
        )
    db.commit()
    db.close()


class QueryCounter:
    def __enter__(self):
        self.n = 0
        event.listen(Engine, "before_cursor_execute", self._hit)
        return self

    def _hit(self, *a, **k):
        self.n += 1

    def __exit__(self, *exc):
        event.remove(Engine, "before_cursor_execute", self._hit)


ENDPOINTS = [
    ("GET", "/repos/{r}/runs", None),
    ("GET", "/repos/{r}/tests", None),
    ("GET", "/repos/{r}/flakiness", None),
    ("GET", "/repos/{r}/impact/graph", None),
    ("POST", "/repos/{r}/impact", {"changed_files": ["pkg/a.py"]}),
    ("GET", "/repos/{r}/failure-clusters", None),
]


def _count(client, repo_id, method, path, body):
    with QueryCounter() as q:
        resp = client.request(method, path.format(r=repo_id), json=body)
    assert resp.status_code == 200, resp.text
    return q.n


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_query_count_is_independent_of_history_size(client, repo_id, method, path, body):
    _seed(repo_id, runs=2)
    small = _count(client, repo_id, method, path, body)
    _seed_more = _seed  # more runs on the same tests
    other = client.post("/repos", json={"name": "big"}).json()["id"]
    _seed_more(other, runs=25, tests=20)
    big = _count(client, other, method, path, body)
    assert big == small, f"{method} {path}: {small} queries at 2 runs vs {big} at 25 runs"


def test_runs_and_tests_are_paginated_with_total_header(client, repo_id):
    _seed(repo_id, runs=7, tests=4)
    r = client.get(f"/repos/{repo_id}/runs", params={"limit": 3, "offset": 2})
    ids = [x["id"] for x in r.json()]
    assert ids == [5, 4, 3] and r.headers["X-Total-Count"] == "7"
    t = client.get(f"/repos/{repo_id}/tests", params={"limit": 2})
    assert len(t.json()) == 2 and t.headers["X-Total-Count"] == "4"
    assert [x["node_id"] for x in client.get(f"/repos/{repo_id}/tests", params={"offset": 3}).json()] == ["m::t3"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 1001}, {"offset": -1}])
def test_bad_page_params_422(client, repo_id, params):
    for kind in ("runs", "tests"):
        assert client.get(f"/repos/{repo_id}/{kind}", params=params).status_code == 422


def test_total_count_header_is_exposed_to_browsers(client, repo_id):
    resp = client.options(
        f"/repos/{repo_id}/runs", headers={"Origin": "http://x", "Access-Control-Request-Method": "GET"}
    )
    assert resp.status_code == 200
    got = client.get(f"/repos/{repo_id}/runs", headers={"Origin": "http://x"})
    assert "x-total-count" in got.headers.get("access-control-expose-headers", "").lower()


def test_listing_runs_does_not_load_coverage_json(client, repo_id):
    _seed(repo_id, runs=3)
    statements = []

    def grab(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", grab)
    try:
        client.get(f"/repos/{repo_id}/runs")
    finally:
        event.remove(Engine, "before_cursor_execute", grab)
    assert statements and not any("coverage_data" in s for s in statements)


def test_commit_filter_uses_the_repo_commit_index(client, repo_id):
    db = _db()
    plan = " ".join(
        str(r)
        for r in db.execute(
            text("EXPLAIN QUERY PLAN SELECT id FROM test_runs WHERE repo_id = 1 AND commit_sha = 'c'")
        )
    )
    assert "ix_test_runs_repo_commit" in plan
    db.close()
