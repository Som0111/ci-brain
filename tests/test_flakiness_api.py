import io


def _junit(cases: list[tuple[str, bool]]) -> bytes:
    """cases: (test_name, passed)"""
    body = ""
    for name, passed in cases:
        if passed:
            body += f'<testcase classname="m" name="{name}" time="0.01" />'
        else:
            body += (
                f'<testcase classname="m" name="{name}" time="0.01">'
                f'<failure message="boom">boom</failure></testcase>'
            )
    return f'<testsuite name="s" tests="{len(cases)}">{body}</testsuite>'.encode()


def _ingest_run(client, repo_id, cases, commit_sha="abc"):
    return client.post(
        f"/repos/{repo_id}/runs",
        files={"junit_xml": ("j.xml", io.BytesIO(_junit(cases)), "text/xml")},
        data={"commit_sha": commit_sha},
    )


def test_stable_test_reports_as_stable(client, repo_id):
    for _ in range(5):
        _ingest_run(client, repo_id, [("test_stable", True)])

    resp = client.get(f"/repos/{repo_id}/flakiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stable_count"] == 1
    assert body["flaky"] == []


def test_flaky_test_reports_with_confidence_and_quarantine(client, repo_id):
    outcomes = [True, False, True, False, True]  # 3 pass / 2 fail -> medium confidence
    for outcome in outcomes:
        _ingest_run(client, repo_id, [("test_flaky", outcome)])

    resp = client.get(f"/repos/{repo_id}/flakiness")
    body = resp.json()
    assert len(body["flaky"]) == 1
    entry = body["flaky"][0]
    assert entry["node_id"] == "m::test_flaky"
    assert entry["pass_count"] == 3
    assert entry["fail_count"] == 2
    assert entry["confidence"] == "medium"
    assert entry["quarantine"] is True


def test_insufficient_data_below_min_runs(client, repo_id):
    _ingest_run(client, repo_id, [("test_new", True)])

    resp = client.get(f"/repos/{repo_id}/flakiness")
    body = resp.json()
    assert len(body["insufficient_data"]) == 1
    assert body["flaky"] == []
    assert body["stable_count"] == 0


def test_commit_sha_filter_scopes_report(client, repo_id):
    for _ in range(5):
        _ingest_run(client, repo_id, [("test_x", True)], commit_sha="commit_a")
    for _ in range(5):
        _ingest_run(client, repo_id, [("test_x", False)], commit_sha="commit_b")

    resp_a = client.get(f"/repos/{repo_id}/flakiness", params={"commit_sha": "commit_a"})
    assert resp_a.json()["stable_count"] == 1
    assert resp_a.json()["flaky"] == []

    resp_all = client.get(f"/repos/{repo_id}/flakiness")
    assert len(resp_all.json()["flaky"]) == 1  # mixed across both commits -> inconsistent


def test_unknown_repo_404s(client):
    resp = client.get("/repos/999/flakiness")
    assert resp.status_code == 404


def test_no_runs_gives_empty_report(client, repo_id):
    resp = client.get(f"/repos/{repo_id}/flakiness")
    body = resp.json()
    assert body == {
        "repo_id": repo_id,
        "commit_sha": None,
        "total_tests": 0,
        "flaky": [],
        "consistently_failing": [],
        "insufficient_data": [],
        "stable_count": 0,
    }
