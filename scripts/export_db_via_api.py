"""Exports a CI Brain database's contents by walking the public API.

Companion to scripts/export_db.py (direct DB connection, complete including
coverage_data). This one needs no DB credentials or network access beyond
normal HTTPS, but the public API never returns TestRun.coverage_data (see
app/api/runs.py), so this export omits it - repos, runs, test cases, and
per-test results are all included and complete; coverage data is not.

Retries on transient failures since the live deploy has shown occasional
502s under load - see the connection-pool fixes in app/database.py.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def get_with_retry(client: httpx.Client, path: str, retries: int = 5, delay: float = 3.0):
    last_exc = None
    for attempt in range(retries):
        try:
            resp = client.get(path, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            last_exc = RuntimeError(f"{path} -> HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            last_exc = exc
        if attempt < retries - 1:
            time.sleep(delay)
    raise RuntimeError(f"Giving up on {path} after {retries} attempts") from last_exc


def enumerate_runs_by_id(client: httpx.Client, repo_id: int, max_id: int, max_misses: int) -> list[dict]:
    """Fallback for when GET /repos/{id}/runs itself fails (observed on the
    live deploy for a repo with enough runs to make that response larger -
    reproducible locally as fine, so this is an environment issue, not an
    app bug - fetching one run at a time via GET /runs/{id} sidesteps it).
    Scans ids 1..max_id, stops early after `max_misses` consecutive 404s
    past the first hit."""
    found = []
    misses_since_last_hit = 0
    seen_any = False
    for run_id in range(1, max_id + 1):
        try:
            resp = client.get(f"/runs/{run_id}", timeout=30)
        except httpx.HTTPError:
            continue
        if resp.status_code == 404:
            if seen_any:
                misses_since_last_hit += 1
                if misses_since_last_hit >= max_misses:
                    break
            continue
        if resp.status_code != 200:
            continue
        detail = resp.json()
        if detail["repo_id"] != repo_id:
            continue
        seen_any = True
        misses_since_last_hit = 0
        found.append(detail)
    return found


def export(api_base: str) -> dict:
    with httpx.Client(base_url=api_base) as client:
        repos = get_with_retry(client, "/repos")

        repos_out = []
        for repo in repos:
            repo_id = repo["id"]
            test_cases = get_with_retry(client, f"/repos/{repo_id}/tests")

            try:
                runs = get_with_retry(client, f"/repos/{repo_id}/runs", retries=2, delay=2.0)
                run_details = [get_with_retry(client, f"/runs/{run['id']}") for run in runs]
            except RuntimeError:
                print(f"  /repos/{repo_id}/runs failing - falling back to per-id enumeration")
                run_details = enumerate_runs_by_id(client, repo_id, max_id=200, max_misses=15)

            runs_out = [
                {
                    "id": detail["id"],
                    "repo_id": detail["repo_id"],
                    "commit_sha": detail["commit_sha"],
                    "branch": detail["branch"],
                    "source": detail["source"],
                    "started_at": detail["started_at"],
                    "finished_at": detail["finished_at"],
                    "created_at": detail["created_at"],
                    "results": [
                        {
                            "node_id": r["test_case"]["node_id"],
                            "file_path": r["test_case"]["file_path"],
                            "status": r["status"],
                            "duration_seconds": r["duration_seconds"],
                            "message": r["message"],
                        }
                        for r in detail["results"]
                    ],
                }
                for detail in run_details
            ]

            repos_out.append({
                **repo,
                "test_cases": test_cases,
                "runs": runs_out,
            })

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_via": "public API (coverage_data not included - not exposed by any endpoint)",
        "api_base": api_base,
        "repos": repos_out,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="https://ci-brain.onrender.com")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data = export(args.api_base)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    total_runs = sum(len(r["runs"]) for r in data["repos"])
    total_results = sum(len(run["results"]) for r in data["repos"] for run in r["runs"])
    print(f"Exported {len(data['repos'])} repo(s), {total_runs} run(s), {total_results} result(s) -> {out_path}")


if __name__ == "__main__":
    main()
