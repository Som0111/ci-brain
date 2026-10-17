from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_junit.xml"


def test_create_repo(client):
    resp = client.post("/repos", json={"name": "r1"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "r1"


def test_create_repo_duplicate_name_conflicts(client):
    client.post("/repos", json={"name": "dup"})
    resp = client.post("/repos", json={"name": "dup"})
    assert resp.status_code == 409


def test_ingest_run_requires_a_file(client, repo_id):
    resp = client.post(f"/repos/{repo_id}/runs")
    assert resp.status_code == 400


def test_ingest_run_unknown_repo_404s(client):
    with open(FIXTURE, "rb") as f:
        resp = client.post("/repos/999/runs", files={"junit_xml": ("sample.xml", f, "text/xml")})
    assert resp.status_code == 404


def test_ingest_junit_run_round_trips(client, repo_id):
    with open(FIXTURE, "rb") as f:
        resp = client.post(
            f"/repos/{repo_id}/runs",
            files={"junit_xml": ("sample.xml", f, "text/xml")},
            data={"commit_sha": "abc123", "branch": "main"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["tests_recorded"] == 4
    assert body["passed"] == 1
    assert body["failed"] == 1
    assert body["error"] == 1
    assert body["skipped"] == 1
    run_id = body["run_id"]

    runs = client.get(f"/repos/{repo_id}/runs").json()
    assert len(runs) == 1
    assert runs[0]["id"] == run_id
    assert runs[0]["commit_sha"] == "abc123"
    assert runs[0]["branch"] == "main"

    tests = client.get(f"/repos/{repo_id}/tests").json()
    assert len(tests) == 4
    node_ids = {t["node_id"] for t in tests}
    assert "tests.test_math::test_divide" in node_ids

    detail = client.get(f"/runs/{run_id}").json()
    assert len(detail["results"]) == 4
    statuses = {r["test_case"]["node_id"]: r["status"] for r in detail["results"]}
    assert statuses["tests.test_math::test_add"] == "passed"
    assert statuses["tests.test_math::test_divide"] == "failed"


def test_ingest_malformed_junit_returns_400(client, repo_id):
    resp = client.post(
        f"/repos/{repo_id}/runs",
        files={"junit_xml": ("bad.xml", b"not xml", "text/xml")},
    )
    assert resp.status_code == 400


def test_re_ingesting_same_tests_reuses_test_case_rows(client, repo_id):
    for _ in range(2):
        with open(FIXTURE, "rb") as f:
            resp = client.post(f"/repos/{repo_id}/runs", files={"junit_xml": ("sample.xml", f, "text/xml")})
            assert resp.status_code == 201

    tests = client.get(f"/repos/{repo_id}/tests").json()
    assert len(tests) == 4  # not 8 — same test_case rows reused across runs

    runs = client.get(f"/repos/{repo_id}/runs").json()
    assert len(runs) == 2


def test_ingest_coverage_only_no_junit(client, repo_id):
    coverage = b'{"files": {"a.py": {"contexts": {"1": ["a.py::test_x|run"]}}}}'
    resp = client.post(
        f"/repos/{repo_id}/runs",
        files={"coverage_json": ("c.json", coverage, "application/json")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["tests_recorded"] == 0  # no JUnit means no TestResult rows, coverage stored on the run alone
    runs = client.get(f"/repos/{repo_id}/runs").json()
    assert runs[0]["source"] == "coverage"


def test_ingest_malformed_coverage_json_400s(client, repo_id):
    resp = client.post(
        f"/repos/{repo_id}/runs",
        files={"coverage_json": ("c.json", b"not json at all", "application/json")},
    )
    assert resp.status_code == 400
    assert "coverage_json" in resp.json()["detail"]


def test_get_run_unknown_404s(client):
    resp = client.get("/runs/999")
    assert resp.status_code == 404


# ---- P0.1 hardening ----

from sqlalchemy import func, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import TestCase, TestResult, TestRun  # noqa: E402

_XML = b'<testsuite><testcase classname="a.test_x" name="t" time="{t}"/></testsuite>'


def _counts(client):
    from app.database import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    try:
        return tuple(db.scalar(select(func.count()).select_from(m)) for m in (TestRun, TestResult, TestCase))
    finally:
        db.close()


def _post(client, repo_id, xml=None, cov=None, **data):
    files = {}
    if xml is not None:
        files["junit_xml"] = ("r.xml", xml, "text/xml")
    if cov is not None:
        files["coverage_json"] = ("c.json", cov, "application/json")
    return client.post(f"/repos/{repo_id}/runs", files=files, data=data)


def test_duplicate_testcase_rejected_with_no_writes(client, repo_id):
    xml = b'<testsuite><testcase classname="a" name="t"/><testcase classname="a" name="t"/></testsuite>'
    resp = _post(client, repo_id, xml)
    assert resp.status_code == 400 and "duplicate" in resp.json()["detail"]
    assert _counts(client) == (0, 0, 0)


def test_parametrized_ids_are_not_duplicates(client, repo_id):
    xml = b'<testsuite><testcase classname="a" name="t[1]"/><testcase classname="a" name="t[2]"/></testsuite>'
    assert _post(client, repo_id, xml).status_code == 201


@pytest.mark.parametrize("t", ["-1", "nan", "inf", "-inf"])
def test_invalid_duration_rejected(client, repo_id, t):
    resp = _post(client, repo_id, _XML.replace(b"{t}", t.encode()))
    assert resp.status_code == 400
    assert _counts(client) == (0, 0, 0)


@pytest.mark.parametrize("fld", ["junit", "coverage"])
def test_oversized_upload_413_no_writes(client, repo_id, monkeypatch, fld):
    monkeypatch.setattr(settings, "max_upload_bytes", 50)
    big = b" " * 200
    resp = _post(client, repo_id, xml=big) if fld == "junit" else _post(client, repo_id, cov=big)
    assert resp.status_code == 413
    assert _counts(client) == (0, 0, 0)


@pytest.mark.parametrize(
    "data", [{"commit_sha": "bad sha!"}, {"commit_sha": "a" * 41}, {"branch": "x" * 256}, {"branch": "a\nb"}]
)
def test_invalid_metadata_rejected(client, repo_id, data):
    assert _post(client, repo_id, _XML.replace(b"{t}", b"1"), **data).status_code == 400
    assert _counts(client) == (0, 0, 0)


@pytest.mark.parametrize(
    "xml",
    [b"", b"<html/>", b'<x:testsuite xmlns:x="urn:x"/>', b"<testsuites/>", b"\xff\xfe junk"],
)
def test_malformed_or_unsupported_junit_is_400(client, repo_id, xml):
    assert _post(client, repo_id, xml).status_code == 400
    assert _counts(client) == (0, 0, 0)


@pytest.mark.parametrize("cov", [b"", b"[]", b'{"files": 1}', b'{"files": {}, "x": NaN}', b"\xff\xfe"])
def test_malformed_coverage_is_400(client, repo_id, cov):
    assert _post(client, repo_id, cov=cov).status_code == 400
    assert _counts(client) == (0, 0, 0)


def test_db_error_mid_ingest_rolls_back_everything(client, repo_id, monkeypatch):
    import app.api.runs as runs

    calls = {"n": 0}
    real = runs._get_or_create_test_case

    def boom(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            from sqlalchemy.exc import OperationalError

            raise OperationalError("stmt", {}, Exception("db gone"))
        return real(*a, **k)

    monkeypatch.setattr(runs, "_get_or_create_test_case", boom)
    xml = b'<testsuite><testcase classname="a" name="1"/><testcase classname="a" name="2"/></testsuite>'
    resp = _post(client, repo_id, xml)
    assert resp.status_code == 503
    assert "db gone" not in resp.text
    assert _counts(client) == (0, 0, 0)


def test_testcase_unique_race_falls_back_to_existing_row(client, repo_id, monkeypatch):
    """Simulate losing the race: the pre-insert lookup misses once although the row exists."""
    _post(client, repo_id, b'<testsuite><testcase classname="a" name="1"/></testsuite>')
    from app.api import runs

    real_scalar = runs.Session.scalar
    state = {"missed": False}

    def flaky_scalar(self, stmt, *a, **k):
        if not state["missed"] and "test_cases" in str(stmt):
            state["missed"] = True
            return None
        return real_scalar(self, stmt, *a, **k)

    monkeypatch.setattr(runs.Session, "scalar", flaky_scalar)
    resp = _post(client, repo_id, b'<testsuite><testcase classname="a" name="1"/></testsuite>')
    assert resp.status_code == 201
    assert _counts(client)[2] == 1
