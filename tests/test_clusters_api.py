import io


def _junit(cases: list[tuple[str, str, str | None]]) -> bytes:
    """cases: (classname, name, failure_message_or_None_for_pass)"""
    body = ""
    for classname, name, message in cases:
        if message is None:
            body += f'<testcase classname="{classname}" name="{name}" time="0.01" />'
        else:
            body += (
                f'<testcase classname="{classname}" name="{name}" time="0.01">'
                f'<failure message="{message}">{message}</failure></testcase>'
            )
    return f'<testsuite name="s" tests="{len(cases)}">{body}</testsuite>'.encode()


def test_no_failures_gives_empty_cluster_list(client, repo_id):
    client.post(
        f"/repos/{repo_id}/runs",
        files={"junit_xml": ("j.xml", io.BytesIO(_junit([("m", "test_ok", None)])), "text/xml")},
    )
    resp = client.get(f"/repos/{repo_id}/failure-clusters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_failures"] == 0
    assert body["clusters"] == []


def test_failures_without_coverage_data_still_cluster(client, repo_id):
    # no coverage_json posted -> no dependency graph entries, covered_files == []
    client.post(
        f"/repos/{repo_id}/runs",
        files={
            "junit_xml": (
                "j.xml",
                io.BytesIO(_junit([("m", "test_a", "assert 1 == 2"), ("m", "test_b", "assert 3 == 4")])),
                "text/xml",
            )
        },
    )
    resp = client.get(f"/repos/{repo_id}/failure-clusters")
    body = resp.json()
    assert body["total_failures"] == 2
    assert len(body["clusters"]) == 1  # same (empty) covered-files key, no call hint
    assert body["clusters"][0]["size"] == 2
    assert body["clusters"][0]["covered_files"] == []


def test_unknown_repo_404s(client):
    resp = client.get("/repos/999/failure-clusters")
    assert resp.status_code == 404


def test_run_id_scopes_to_one_run(client, repo_id):
    r1 = client.post(
        f"/repos/{repo_id}/runs",
        files={"junit_xml": ("j.xml", io.BytesIO(_junit([("m", "test_a", "assert 1 == 2")])), "text/xml")},
    )
    r2 = client.post(
        f"/repos/{repo_id}/runs",
        files={"junit_xml": ("j.xml", io.BytesIO(_junit([("m", "test_a", "assert 1 == 2")])), "text/xml")},
    )
    run1_id = r1.json()["run_id"]

    resp = client.get(f"/repos/{repo_id}/failure-clusters", params={"run_id": run1_id})
    assert resp.json()["total_failures"] == 1  # not 2, despite two runs total

    resp_all = client.get(f"/repos/{repo_id}/failure-clusters")
    assert resp_all.json()["total_failures"] == 2
