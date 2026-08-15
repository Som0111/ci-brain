"""
Clone the benchmark target repo (toolz) and install it into its own isolated venv.

Pinned to a fixed commit so replay results stay reproducible across the whole
project instead of drifting if upstream toolz gets new commits.

Supports cloning multiple named `variant`s of the same pinned commit into
separate directories (e.g. "toolz" = clean baseline, "toolz-flaky-seed" =
Phase 3's seeded-flaky copy, "toolz-bug-seed" = Phase 5's seeded-bug copy) so
seeded chaos never touches the clean baseline data other phases read from.
"""
import argparse
import subprocess
import sys
import venv
from pathlib import Path

TARGET_REPO_URL = "https://github.com/pytoolz/toolz.git"
TARGET_COMMIT = "568c2b8393973cd172a466546c9d95779c452438"
TARGET_REPOS_ROOT = Path(__file__).resolve().parent.parent / "target_repos"


def target_dir(variant: str = "toolz") -> Path:
    return TARGET_REPOS_ROOT / variant


def run(cmd, cwd=None):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def setup(variant: str = "toolz") -> Path:
    tdir = target_dir(variant)

    if tdir.exists():
        print(f"{tdir} already exists, checking out pinned commit.")
        run(["git", "fetch", "--quiet"], cwd=tdir)
    else:
        tdir.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--quiet", TARGET_REPO_URL, str(tdir)])

    run(["git", "checkout", "--quiet", TARGET_COMMIT], cwd=tdir)

    venv_dir = tdir / ".venv"
    if not venv_dir.exists():
        print(f"Creating venv at {venv_dir}")
        venv.EnvBuilder(with_pip=True).create(venv_dir)

    py = venv_dir / "Scripts" / "python.exe" if sys.platform == "win32" else venv_dir / "bin" / "python"
    run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    run([str(py), "-m", "pip", "install", "--quiet", "-e", str(tdir), "pytest", "coverage", "pytest-cov"])

    print(f"\nTarget repo ready at {tdir} (pinned to {TARGET_COMMIT[:8]})")
    return tdir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="toolz", help="subdirectory name under target_repos/")
    args = parser.parse_args()
    setup(args.variant)


if __name__ == "__main__":
    main()
