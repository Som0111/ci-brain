def test_benchmark_returns_recorded_results(client):
    resp = client.get("/benchmark")
    assert resp.status_code == 200
    body = resp.json()
    assert body["variant"] == "toolz"
    assert len(body["scenarios"]) == 4
    assert all("runtime_reduction_pct" in s for s in body["scenarios"])
