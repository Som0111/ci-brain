"""Full pipeline integration test: ingestion -> flakiness -> impact -> clustering,
all through the public API, using nothing but what a real CI run would produce.

This is the Phase 6 checklist item verifying the pieces built in Phases 1-5
actually work together as one system, not just individually.
"""
import io
import json


def _junit(cases: list[tuple[str, str, str | None]]) -> bytes:
    """cases: (classname, name, failure_message_or_None)"""
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


def _coverage(file_to_contexts: dict[str, list[str]]) -> bytes:
    files = {path: {"contexts": {"1": ctxs}} for path, ctxs in file_to_contexts.items()}
    return json.dumps({"files": files}).encode()


def test_full_pipeline_ingestion_through_all_analyses(client):
    # 1. Create the repo
    resp = client.post("/repos", json={"name": "pipeline-repo", "url": "https://example.com/pipeline"})
    assert resp.status_code == 201
    repo_id = resp.json()["id"]

    # 2. Ingest 5 identical-commit runs: test_stable always passes, test_flaky
    #    flips, test_broken always fails. Each covers a distinct source file,
    #    so impact analysis has real structure to select from.
    outcomes = [True, False, True, False, True]  # test_flaky pattern
    for passed in outcomes:
        cases = [
            ("pkg.tests.test_a", "test_stable", None),
            ("pkg.tests.test_a", "test_flaky", None if passed else "assert 1 == 2"),
            ("pkg.tests.test_b", "test_broken", "assert None == 5"),
        ]
        coverage = {
            "pkg/mod_a.py": ["pkg/tests/test_a.py::test_stable|run", "pkg/tests/test_a.py::test_flaky|run"],
            "pkg/mod_b.py": ["pkg/tests/test_b.py::test_broken|run"],
        }
        resp = client.post(
            f"/repos/{repo_id}/runs",
            files={
                "junit_xml": ("j.xml", io.BytesIO(_junit(cases)), "text/xml"),
                "coverage_json": ("c.json", io.BytesIO(_coverage(coverage)), "application/json"),
            },
            data={"commit_sha": "same_commit"},
        )
        assert resp.status_code == 201

    # 3. Query endpoints round-trip: runs, tests
    assert len(client.get(f"/repos/{repo_id}/runs").json()) == 5
    assert len(client.get(f"/repos/{repo_id}/tests").json()) == 3

    # 4. Flakiness: test_flaky should be flagged, test_stable and test_broken should not
    flakiness = client.get(f"/repos/{repo_id}/flakiness").json()
    flaky_names = {e["node_id"].split("::")[-1] for e in flakiness["flaky"]}
    assert flaky_names == {"test_flaky"}
    assert flakiness["stable_count"] == 1  # test_stable
    assert len(flakiness["consistently_failing"]) == 1  # test_broken

    # 5. Impact analysis: changing mod_a.py should select only pkg.tests.test_a's tests
    impact = client.post(f"/repos/{repo_id}/impact", json={"changed_files": ["pkg/mod_a.py"]}).json()
    assert impact["full_suite_fallback"] is False
    selected_short = {t.split("::")[-1] for t in impact["selected_tests"]}
    assert selected_short == {"test_stable", "test_flaky"}
    assert "test_broken" not in " ".join(impact["selected_tests"])

    # 6. Failure clustering: test_broken's failures should form their own cluster
    clusters = client.get(f"/repos/{repo_id}/failure-clusters").json()
    assert clusters["total_failures"] == 5 + 2  # test_broken x5, test_flaky x2 fails
    broken_cluster = next(
        c for c in clusters["clusters"] if any("test_broken" in t for t in c["tests"])
    )
    assert broken_cluster["size"] == 5
    assert broken_cluster["covered_files"] == ["pkg/mod_b.py"]
