from pathlib import Path

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
