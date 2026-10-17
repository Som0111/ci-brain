import io

import pytest

BAD_REPOS = [{"name": ""}, {"name": "   "}, {"name": "x" * 256}, {"name": "a", "url": "u" * 501}, {}]


@pytest.mark.parametrize("body", BAD_REPOS)
def test_bad_repo_payload_422(client, body):
    assert client.post("/repos", json=body).status_code == 422


def test_repo_name_trimmed_and_blank_url_nulled(client):
    r = client.post("/repos", json={"name": "  r  ", "url": "  "}).json()
    assert r["name"] == "r" and r["url"] is None
    assert client.post("/repos", json={"name": "r"}).status_code == 409  # trimmed dup


def test_repo_create_integrity_race_returns_409(client, monkeypatch):
    client.post("/repos", json={"name": "race"})
    import app.api.repos as repos

    monkeypatch.setattr(repos.Session, "scalar", lambda self, *a, **k: None)  # existence check "misses"
    assert client.post("/repos", json={"name": "race"}).status_code == 409


@pytest.mark.parametrize(
    "files", [[], [""], ["  "], ["a.py"] * 1001, ["x" * 1001], "notalist"]
)
def test_bad_changed_files_422(client, repo_id, files):
    assert client.post(f"/repos/{repo_id}/impact", json={"changed_files": files}).status_code == 422


def test_422_does_not_echo_input(client, repo_id):
    resp = client.post(f"/repos/{repo_id}/impact", json={"changed_files": "SECRET-VALUE"})
    assert "SECRET-VALUE" not in resp.text
    assert isinstance(resp.json()["detail"], list)


@pytest.mark.parametrize(
    "params",
    [{"min_cluster_size": 0}, {"min_cluster_size": -1}, {"max_clusters": 0}, {"max_clusters": 21}, {"run_id": 0}],
)
def test_summarize_bounds_422(client, repo_id, params):
    assert client.post(f"/repos/{repo_id}/failure-clusters/summarize", params=params).status_code == 422


def test_invalid_ids_and_types(client):
    assert client.get("/repos/abc").status_code == 422
    assert client.get("/runs/abc").status_code == 422
    assert client.get("/repos/999").status_code == 404


def _ingest(client, repo_id, name="t"):
    xml = f'<testsuite><testcase classname="a" name="{name}"><failure message="m"/></testcase></testsuite>'
    return client.post(
        f"/repos/{repo_id}/runs", files={"junit_xml": ("j.xml", io.BytesIO(xml.encode()), "text/xml")}
    ).json()["run_id"]


def test_cluster_scope_validation(client, repo_id):
    run_id = _ingest(client, repo_id)
    other = client.post("/repos", json={"name": "other"}).json()["id"]
    url = f"/repos/{repo_id}/failure-clusters"
    assert client.get(url, params={"run_id": 9999}).status_code == 404
    assert client.get(f"/repos/{other}/failure-clusters", params={"run_id": run_id}).status_code == 404
    assert client.get(url, params={"baseline_repo_id": 9999}).status_code == 404
    assert client.get(url, params={"baseline_repo_id": other}).status_code == 400  # no shared tests
    _ingest(client, other)  # now shares a.t
    assert client.get(url, params={"baseline_repo_id": other}).status_code == 200
    assert client.get(url, params={"baseline_repo_id": repo_id, "run_id": run_id}).status_code == 200


def test_unhandled_error_is_generic_500(client, monkeypatch):
    from fastapi.testclient import TestClient

    import app.api.repos as repos
    from app.main import app

    def boom(*a, **k):
        raise RuntimeError("db password=hunter2")

    monkeypatch.setattr(repos.Session, "scalar", boom)
    resp = TestClient(app, raise_server_exceptions=False).post("/repos", json={"name": "x"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "internal server error"}


def test_openapi_documents_ingest_errors(client):
    spec = client.get("/openapi.json").json()
    codes = spec["paths"]["/repos/{repo_id}/runs"]["post"]["responses"]
    assert {"201", "413", "400", "404"} <= set(codes)
