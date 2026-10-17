"""P1 item 9: classification edge cases, commit scoping warning, run_key idempotency."""

import io

import pytest

from app.analysis.classify import MIN_RUNS, Confidence, Verdict, classify
from app.analysis.flakiness import TestVarianceStats as Stats


def _s(p=0, f=0, s=0):
    return classify(Stats("t", "t.py", pass_count=p, fail_count=f, skip_count=s))


@pytest.mark.parametrize(
    "p,f,s,verdict",
    [
        (0, 0, 0, Verdict.INSUFFICIENT_DATA),  # no observations
        (1, 0, 0, Verdict.INSUFFICIENT_DATA),  # one observation
        (0, 0, 50, Verdict.INSUFFICIENT_DATA),  # all skipped
        (MIN_RUNS - 1, 0, 0, Verdict.INSUFFICIENT_DATA),
        (MIN_RUNS, 0, 0, Verdict.STABLE),
        (0, MIN_RUNS, 0, Verdict.CONSISTENTLY_FAILING),
        (MIN_RUNS - 1, 1, 0, Verdict.FLAKY),
        (3, 2, 0, Verdict.FLAKY),
        (2, 2, 100, Verdict.INSUFFICIENT_DATA),  # skips never rescue a thin sample
    ],
)
def test_verdict_boundaries(p, f, s, verdict):
    assert _s(p, f, s).verdict == verdict


@pytest.mark.parametrize(
    "p,f,conf,quarantine",
    [
        (99, 1, Confidence.LOW, False),
        (98, 2, Confidence.MEDIUM, True),
        (97, 3, Confidence.HIGH, True),
        (3, 97, Confidence.HIGH, True),
    ],
)
def test_confidence_comes_from_minority_count_and_gates_quarantine(p, f, conf, quarantine):
    c = _s(p, f)
    assert (c.confidence, c.quarantine) == (conf, quarantine)


def _xml(name, ok=True, kind="failure"):
    inner = "" if ok else f'<{kind} message="m"/>'
    return f'<testsuite><testcase classname="m" name="{name}">{inner}</testcase></testsuite>'.encode()


def _post(client, repo_id, xml, **data):
    return client.post(f"/repos/{repo_id}/runs", files={"junit_xml": ("j.xml", io.BytesIO(xml), "text/xml")}, data=data)


def test_error_status_counts_as_fail_and_uneven_run_counts(client, repo_id):
    for i in range(5):
        _post(client, repo_id, _xml("a", ok=i % 2 == 0, kind="error"), commit_sha="c1")
    for _ in range(2):  # 'b' only appears in 2 runs -> insufficient
        _post(client, repo_id, _xml("b"), commit_sha="c1")
    body = client.get(f"/repos/{repo_id}/flakiness").json()
    flaky = {e["node_id"]: e for e in body["flaky"]}
    assert flaky["m::a"]["fail_count"] == 2 and flaky["m::a"]["pass_count"] == 3
    assert [e["node_id"] for e in body["insufficient_data"]] == ["m::b"]


def test_mixed_commits_produce_warning_and_commit_filter_removes_it(client, repo_id):
    for i in range(5):
        _post(client, repo_id, _xml("a", ok=i < 3), commit_sha=f"c{i % 2}")
    body = client.get(f"/repos/{repo_id}/flakiness").json()
    assert body["commits_seen"] == 2 and "commit_sha" in body["warning"]
    scoped = client.get(f"/repos/{repo_id}/flakiness", params={"commit_sha": "c0"}).json()
    assert scoped["warning"] is None and scoped["commits_seen"] == 1


def test_single_commit_has_no_warning_but_missing_commit_mixed_in_does(client, repo_id):
    _post(client, repo_id, _xml("a"), commit_sha="c1")
    assert client.get(f"/repos/{repo_id}/flakiness").json()["warning"] is None
    _post(client, repo_id, _xml("a"))  # no commit_sha
    assert "without a commit_sha" in client.get(f"/repos/{repo_id}/flakiness").json()["warning"]


def test_run_key_makes_retries_idempotent_and_not_extra_evidence(client, repo_id):
    first = _post(client, repo_id, _xml("a", ok=False), commit_sha="c1", run_key="gh-1-attempt1")
    assert first.status_code == 201 and first.json()["duplicate"] is False
    retry = _post(client, repo_id, _xml("a", ok=False), commit_sha="c1", run_key="gh-1-attempt1")
    assert retry.status_code == 200
    body = retry.json()
    assert body["duplicate"] is True and body["run_id"] == first.json()["run_id"] and body["failed"] == 1
    assert len(client.get(f"/repos/{repo_id}/runs").json()) == 1
    flaky = client.get(f"/repos/{repo_id}/flakiness").json()
    assert flaky["insufficient_data"][0]["fail_count"] == 1  # counted once, not twice


def test_run_key_is_per_repo_and_optional(client, repo_id):
    other = client.post("/repos", json={"name": "other"}).json()["id"]
    assert _post(client, repo_id, _xml("a"), run_key="k").status_code == 201
    assert _post(client, other, _xml("a"), run_key="k").status_code == 201  # same key, different repo
    assert _post(client, repo_id, _xml("a")).status_code == 201  # no key: never deduplicated
    assert _post(client, repo_id, _xml("a")).status_code == 201


def test_run_key_validation(client, repo_id):
    assert _post(client, repo_id, _xml("a"), run_key="x" * 129).status_code == 400
    assert _post(client, repo_id, _xml("a"), run_key="a\nb").status_code == 400


def test_run_key_race_resolves_to_duplicate(client, repo_id, monkeypatch):
    """Lost race: the pre-check misses, the unique constraint fires, the retry path returns the winner."""
    _post(client, repo_id, _xml("a"), run_key="race")
    import app.api.runs as runs

    real = runs._existing_run_result
    calls = {"n": 0}

    def flaky_lookup(db, rid, key):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(db, rid, key)

    monkeypatch.setattr(runs, "_existing_run_result", flaky_lookup)
    resp = _post(client, repo_id, _xml("a"), run_key="race")
    assert resp.status_code == 200 and resp.json()["duplicate"] is True
    assert len(client.get(f"/repos/{repo_id}/runs").json()) == 1


def test_coverage_only_run_key_dedupes(client, repo_id):
    cov = b'{"files": {}}'
    args = {"coverage_json": ("c.json", cov, "application/json")}
    assert client.post(f"/repos/{repo_id}/runs", files=args, data={"run_key": "c"}).status_code == 201
    assert client.post(f"/repos/{repo_id}/runs", files=args, data={"run_key": "c"}).status_code == 200
