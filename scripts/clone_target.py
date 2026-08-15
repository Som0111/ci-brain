"""
Clone the benchmark target repo (toolz) and install it into its own isolated venv.

Pinned to a fixed commit so replay results stay reproducible across the whole
project (Phases 2-5 all replay this same repo state) instead of drifting if
upstream toolz gets new commits.
"""
import subprocess
import sys
import venv
from pathlib import Path

TARGET_REPO_URL = "https://github.com/pytoolz/toolz.git"
TARGET_COMMIT = "568c2b8393973cd172a466546c9d95779c452438"
TARGET_DIR = Path(__file__).resolve().parent.parent / "target_repos" / "toolz"


def run(cmd, cwd=None):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    if TARGET_DIR.exists():
        print(f"{TARGET_DIR} already exists, checking out pinned commit.")
        run(["git", "fetch", "--quiet"], cwd=TARGET_DIR)
    else:
        TARGET_DIR.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--quiet", TARGET_REPO_URL, str(TARGET_DIR)])

    run(["git", "checkout", "--quiet", TARGET_COMMIT], cwd=TARGET_DIR)

    venv_dir = TARGET_DIR / ".venv"
    if not venv_dir.exists():
        print(f"Creating venv at {venv_dir}")
        venv.EnvBuilder(with_pip=True).create(venv_dir)

    pip = venv_dir / "Scripts" / "pip.exe" if sys.platform == "win32" else venv_dir / "bin" / "pip"
    run([str(pip), "install", "--quiet", "--upgrade", "pip"])
    run([str(pip), "install", "--quiet", "-e", str(TARGET_DIR), "pytest", "coverage", "pytest-cov"])

    print(f"\nTarget repo ready at {TARGET_DIR} (pinned to {TARGET_COMMIT[:8]})")


if __name__ == "__main__":
    main()
