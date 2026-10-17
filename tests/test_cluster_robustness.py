"""P1 item 10: clustering/summarize robustness and heuristic-vs-evidence labelling."""

import io
import json
import time
from unittest.mock import patch

import pytest

from app.analysis.clustering import FailureRecord, cluster_failures, extract_call_hint
from app.analysis.summarize import ClusterSummary
from app.parsers.junit import MAX_MESSAGE_CHARS, parse_junit_xml


def _junit(cases):
    """cases: (classname, name, message_or_None)"""
    body = ""
    for c, n, m in cases:
        inner = "" if m is None else f'<failure message="{m}"/>'
        body += f'<testcase classname="{c}" name="{n}">{inner}</testcase>'
    return f"<testsuite>{body}</testsuite>".encode()


def _post(client, repo_id, xml, **data):
    return client.post(f"/repos/{repo_id}/runs", files={"junit_xml": ("j.xml", io.BytesIO(xml), "text/xml")}, data=data)


def test_empty_messages_cluster_without_crashing():
    fails = [FailureRecord("a::t1", "a.py", ""), FailureRecord("a::t2", "a.py", "")]
    (c,) = cluster_failures(fails, {})
    assert c.size == 2 and c.representative.message == "" and c.call_hint is None


def test_huge_traceback_is_capped_at_ingest_and_hint_extraction_is_fast():
    huge = "x" * 5_000_000 + " where 1 = first(...)"
    (r,) = parse_junit_xml(_junit([("m", "t", huge)]))
    assert len(r.message) <= MAX_MESSAGE_CHARS + 20 and r.message.endswith("[truncated]")
    start = time.perf_counter()
    extract_call_hint("where " * 50_000)  # pathological repetition
    assert time.perf_counter() - start < 2


def test_repeated_failures_across_runs_count_records_but_report_distinct_tests(client, repo_id):
    for _ in range(3):
        _post(client, repo_id, _junit([("m", "a", "boom"), ("m", "b", "boom")]))
    (cl,) = client.get(f"/repos/{repo_id}/failure-clusters").json()["clusters"]
    assert cl["size"] == 6 and cl["distinct_tests"] == 2
    scoped = client.get(f"/repos/{repo_id}/failure-clusters", params={"run_id": 1}).json()["clusters"][0]
    assert scoped["size"] == 2


def test_absent_coverage_is_flagged_and_response_is_labelled_heuristic(client, repo_id):
    _post(client, repo_id, _junit([("m", "a", "boom")]))
    body = client.get(f"/repos/{repo_id}/failure-clusters").json()
    assert "NOT confirmed root causes" in body["note"]
    assert body["clusters"][0]["has_coverage"] is False and body["clusters"][0]["covered_files"] == []


def test_same_file_independent_bugs_share_a_cluster_known_limitation():
    cov = {"a::t1": frozenset({"f.py"}), "a::t2": frozenset({"f.py"})}
    fails = [FailureRecord("a::t1", "a.py", "assert 1 == 2"), FailureRecord("a::t2", "a.py", "assert 'x' == 'y'")]
    assert len(cluster_failures(fails, cov)) == 1  # documented limitation, see clustering.py docstring


def test_oversized_stored_message_is_truncated_in_response(client, repo_id, monkeypatch):
    _post(client, repo_id, _junit([("m", "a", "y" * 10_000)]))
    msg = client.get(f"/repos/{repo_id}/failure-clusters").json()["clusters"][0]["representative_message"]
    assert len(msg) == 2000


def test_summarize_without_gemini_key_is_200_with_per_cluster_error(client, repo_id):
    _post(client, repo_id, _junit([("m", "a", "boom"), ("m", "b", "boom")]))
    resp = client.post(f"/repos/{repo_id}/failure-clusters/summarize")
    assert resp.status_code == 200
    c = resp.json()["clusters"][0]
    assert c["hypothesis"] is None and "GEMINI_API_KEY" in c["llm_error"]
    assert "model-generated" in resp.json()["note"]


def test_empty_message_cluster_is_not_sent_to_the_model(client, repo_id):
    _post(client, repo_id, _junit([("m", "a", ""), ("m", "b", "")]))
    with patch("app.api.clusters.summarize_cluster") as mock:
        c = client.post(f"/repos/{repo_id}/failure-clusters/summarize").json()["clusters"][0]
    mock.assert_not_called()
    assert c["hypothesis"] is None and "no failure message" in c["llm_error"]


def test_summarize_success_marks_hypothesis_and_leaves_observed_fields_untouched(client, repo_id):
    _post(client, repo_id, _junit([("m", "a", "boom"), ("m", "b", "boom")]))
    free = client.get(f"/repos/{repo_id}/failure-clusters").json()["clusters"][0]
    with patch("app.api.clusters.summarize_cluster", return_value=ClusterSummary("guess", "fake")):
        got = client.post(f"/repos/{repo_id}/failure-clusters/summarize").json()["clusters"][0]
    assert got["hypothesis"] == "guess"
    assert {k: got[k] for k in free} == free


def test_openapi_distinguishes_observed_from_model_generated(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert "MODEL-GENERATED" in schemas["SummarizedClusterEntry"]["properties"]["hypothesis"]["description"]
    assert "OBSERVED" in schemas["ClusterEntry"]["properties"]["covered_files"]["description"]


@pytest.mark.parametrize("message,hint", [("", None), (None, None), ("where 1 = first(x)", "first")])
def test_extract_call_hint_inputs(message, hint):
    assert extract_call_hint(message) == hint


def test_json_serialisable_report(client, repo_id):
    _post(client, repo_id, _junit([("m", "a", "boom")]))
    json.dumps(client.get(f"/repos/{repo_id}/failure-clusters").json())
