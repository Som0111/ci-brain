import io
from unittest.mock import patch

from app.analysis.summarize import ClusterSummary, SummarizerNotConfigured


def _junit(cases: list[tuple[str, str, str | None]]) -> bytes:
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


def test_summarize_calls_llm_once_per_eligible_cluster(client, repo_id):
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

    with patch(
        "app.api.clusters.summarize_cluster",
        return_value=ClusterSummary(hypothesis="looks like a dropped-value bug", model="fake-model"),
    ) as mock_summarize:
        resp = client.post(f"/repos/{repo_id}/failure-clusters/summarize")

    assert resp.status_code == 200
    body = resp.json()
    assert body["clusters_summarized"] == 1  # both failures share one (empty) covered-files key
    assert body["clusters"][0]["hypothesis"] == "looks like a dropped-value bug"
    assert mock_summarize.call_count == 1  # exactly one LLM call for this one cluster


def test_min_cluster_size_skips_small_clusters_without_calling_llm(client, repo_id):
    client.post(
        f"/repos/{repo_id}/runs",
        files={"junit_xml": ("j.xml", io.BytesIO(_junit([("m", "test_a", "assert 1 == 2")])), "text/xml")},
    )

    with patch("app.api.clusters.summarize_cluster") as mock_summarize:
        resp = client.post(f"/repos/{repo_id}/failure-clusters/summarize", params={"min_cluster_size": 2})

    body = resp.json()
    assert body["clusters_summarized"] == 0
    assert body["clusters_skipped"] == 1
    assert mock_summarize.call_count == 0  # cost-bounding must actually prevent the call


def test_max_clusters_caps_llm_calls(client, repo_id):
    cases = []
    for i in range(3):
        cases.append((f"mod{i}", "test_x", "assert 1 == 2"))
        cases.append((f"mod{i}", "test_y", "assert 1 == 2"))
    client.post(f"/repos/{repo_id}/runs", files={"junit_xml": ("j.xml", io.BytesIO(_junit(cases)), "text/xml")})

    with patch(
        "app.api.clusters.summarize_cluster",
        return_value=ClusterSummary(hypothesis="h", model="fake"),
    ) as mock_summarize:
        resp = client.post(f"/repos/{repo_id}/failure-clusters/summarize", params={"max_clusters": 1})

    assert resp.json()["clusters_summarized"] == 1
    assert mock_summarize.call_count == 1


def test_not_configured_reports_error_without_500(client, repo_id):
    client.post(
        f"/repos/{repo_id}/runs",
        files={"junit_xml": ("j.xml", io.BytesIO(_junit([("m", "test_a", "assert 1 == 2")])), "text/xml")},
    )

    with patch("app.api.clusters.summarize_cluster", side_effect=SummarizerNotConfigured("no key")):
        resp = client.post(f"/repos/{repo_id}/failure-clusters/summarize", params={"min_cluster_size": 1})

    assert resp.status_code == 200
    entry = resp.json()["clusters"][0]
    assert entry["hypothesis"] is None
    assert entry["llm_error"] == "no key"
