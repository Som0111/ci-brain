import io
import json


def _junit(cases: list[tuple[str, str]]) -> bytes:
    body = "".join(f'<testcase classname="{c}" name="{n}" time="0.01" />' for c, n in cases)
    return f'<testsuite name="s" tests="{len(cases)}">{body}</testsuite>'.encode()


def _coverage(file_to_test_context: dict[str, str]) -> bytes:
    files = {
        path: {"contexts": {"1": [ctx]}}
        for path, ctx in file_to_test_context.items()
    }
    return json.dumps({"files": files}).encode()


def _ingest(client, repo_id, cases, coverage):
    return client.post(
        f"/repos/{repo_id}/runs",
        files={
            "junit_xml": ("j.xml", io.BytesIO(_junit(cases)), "text/xml"),
            "coverage_json": ("c.json", io.BytesIO(_coverage(coverage)), "application/json"),
        },
    )


def test_impact_selects_only_covering_tests(client, repo_id):
    resp = _ingest(
        client, repo_id,
        cases=[("pkg.tests.test_a", "test_x"), ("pkg.tests.test_b", "test_y")],
        coverage={"pkg/mod.py": "pkg/tests/test_a.py::test_x|run"},
    )
    assert resp.status_code == 201

    resp = client.post(f"/repos/{repo_id}/impact", json={"changed_files": ["pkg/mod.py"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_suite_fallback"] is False
    assert body["selected_tests"] == ["pkg.tests.test_a::test_x"]
    assert body["total_tests"] == 2
    assert body["selected_count"] == 1
    assert body["reduction_pct"] == 50.0


def test_impact_config_file_falls_back_to_full_suite(client, repo_id):
    _ingest(
        client, repo_id,
        cases=[("pkg.tests.test_a", "test_x")],
        coverage={"pkg/mod.py": "pkg/tests/test_a.py::test_x|run"},
    )
    resp = client.post(f"/repos/{repo_id}/impact", json={"changed_files": ["conftest.py"]})
    body = resp.json()
    assert body["full_suite_fallback"] is True
    assert body["selected_count"] == body["total_tests"]


def test_impact_unknown_repo_404s(client):
    resp = client.post("/repos/999/impact", json={"changed_files": ["x.py"]})
    assert resp.status_code == 404


def test_impact_no_changed_files_selects_nothing(client, repo_id):
    _ingest(
        client, repo_id,
        cases=[("pkg.tests.test_a", "test_x")],
        coverage={"pkg/mod.py": "pkg/tests/test_a.py::test_x|run"},
    )
    resp = client.post(f"/repos/{repo_id}/impact", json={"changed_files": []})
    body = resp.json()
    assert body["selected_count"] == 0
    assert body["full_suite_fallback"] is False


def test_graph_summary_reflects_ingested_coverage(client, repo_id):
    _ingest(
        client, repo_id,
        cases=[("pkg.tests.test_a", "test_x"), ("pkg.tests.test_a", "test_y")],
        coverage={"pkg/mod.py": "pkg/tests/test_a.py::test_x|run"},
    )
    resp = client.get(f"/repos/{repo_id}/impact/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["files"] == 1
    assert body["edges"] == 1
    assert body["file_test_counts"] == {"pkg/mod.py": 1}


def test_graph_summary_unknown_repo_404s(client):
    resp = client.get("/repos/999/impact/graph")
    assert resp.status_code == 404


def test_graph_summary_no_data_is_empty_not_error(client, repo_id):
    resp = client.get(f"/repos/{repo_id}/impact/graph")
    assert resp.status_code == 200
    assert resp.json() == {"repo_id": repo_id, "files": 0, "edges": 0, "file_test_counts": {}}
