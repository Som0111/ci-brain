def test_list_repos_empty(client):
    resp = client.get("/repos")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_repos_returns_created_repos(client, repo_id):
    client.post("/repos", json={"name": "another-repo"})
    resp = client.get("/repos")
    names = {r["name"] for r in resp.json()}
    assert names == {"sample-repo", "another-repo"}


def test_get_repo_by_id(client, repo_id):
    resp = client.get(f"/repos/{repo_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == repo_id
    assert resp.json()["name"] == "sample-repo"


def test_get_repo_unknown_404s(client):
    resp = client.get("/repos/999")
    assert resp.status_code == 404


def test_create_repo_without_url(client):
    resp = client.post("/repos", json={"name": "no-url-repo"})
    assert resp.status_code == 201
    assert resp.json()["url"] is None
