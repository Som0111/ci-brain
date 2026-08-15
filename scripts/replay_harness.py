"""
Run one variant of the target repo's suite N times and push each run through
the Phase 1 ingestion API (POST /repos/{repo_id}/runs).

Requires the CI Brain API to already be running (see DEVELOPER_GUIDE.md).

`--repo-name` controls which logical Repo the runs are stored under in CI
Brain's own DB. Seeded variants (flaky, buggy) use their own repo name so
their noisy/failing runs never mix into the clean "toolz" baseline that
Phase 4's dependency graph is built from.
"""
import argparse
from pathlib import Path

import httpx

from scripts.clone_target import TARGET_COMMIT
from scripts.run_target_tests import run_once

REPLAY_DIR = Path(__file__).resolve().parent.parent / "replay_data"
REPO_URL = "https://github.com/pytoolz/toolz"


def ensure_repo(client: httpx.Client, repo_name: str) -> int:
    resp = client.get("/repos")
    resp.raise_for_status()
    for repo in resp.json():
        if repo["name"] == repo_name:
            return repo["id"]

    resp = client.post("/repos", json={"name": repo_name, "url": REPO_URL})
    resp.raise_for_status()
    return resp.json()["id"]


def push_run(client: httpx.Client, repo_id: int, run_dir: Path) -> dict:
    with (run_dir / "junit.xml").open("rb") as junit_f, (run_dir / "coverage.json").open("rb") as cov_f:
        resp = client.post(
            f"/repos/{repo_id}/runs",
            files={
                "junit_xml": ("junit.xml", junit_f, "application/xml"),
                "coverage_json": ("coverage.json", cov_f, "application/json"),
            },
            data={"commit_sha": TARGET_COMMIT, "branch": "benchmark"},
        )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=5, help="number of replay runs")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--variant", default="toolz", help="target_repos/ subdirectory to run")
    parser.add_argument("--repo-name", default="toolz", help="Repo name to store runs under in CI Brain's DB")
    parser.add_argument("--out-prefix", default="run", help="replay_data/<prefix>_N output dir prefix")
    args = parser.parse_args()

    with httpx.Client(base_url=args.api_base, timeout=30.0) as client:
        repo_id = ensure_repo(client, args.repo_name)
        print(f"repo_id={repo_id} ({args.repo_name}), variant={args.variant}")

        for i in range(1, args.n + 1):
            run_dir = REPLAY_DIR / f"{args.out_prefix}_{i}"
            print(f"\n--- replay run {i}/{args.n} ---")
            returncode = run_once(run_dir, args.variant)
            result = push_run(client, repo_id, run_dir)
            print(
                f"run_id={result['run_id']} exit={returncode} "
                f"passed={result['passed']} failed={result['failed']} "
                f"skipped={result['skipped']} error={result['error']}"
            )


if __name__ == "__main__":
    main()
