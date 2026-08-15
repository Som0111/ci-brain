"""
Run one variant of the target repo's test suite once, capturing:
  - JUnit XML (pass/fail/duration per test)
  - coverage.py data with per-test contexts (which test executed which line)

The contexts data is what Phase 4's dependency graph gets built from, so we
export it explicitly via `coverage json --show-contexts` rather than relying
on pytest-cov's default report.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from scripts.clone_target import target_dir


def target_python(variant: str = "toolz") -> Path:
    venv_dir = target_dir(variant) / ".venv"
    return venv_dir / "Scripts" / "python.exe" if sys.platform == "win32" else venv_dir / "bin" / "python"


def run_once(out_dir: Path, variant: str = "toolz") -> int:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tdir = target_dir(variant)
    py = target_python(variant)

    coverage_data_file = tdir / ".coverage"
    coverage_data_file.unlink(missing_ok=True)

    # coverage.py's default "sysmon" tracer (Python 3.12+) doesn't fully support
    # per-test dynamic contexts and raises a warning-as-error under toolz's
    # filterwarnings=error config. The classic tracer handles contexts correctly.
    env = {**os.environ, "COVERAGE_CORE": "ctrace"}

    result = subprocess.run(
        [
            str(py), "-m", "pytest", "toolz/",
            f"--junitxml={out_dir / 'junit.xml'}",
            "-q",
            "--color=no",  # otherwise pytest's ANSI escapes end up inside stored failure messages
            "--cov=toolz",
            "--cov-context=test",
            "--cov-report=",
        ],
        cwd=tdir,
        env=env,
    )

    subprocess.run(
        [str(py), "-m", "coverage", "json", "--show-contexts", "-o", str(out_dir / "coverage.json")],
        cwd=tdir,
        env=env,
        check=True,
    )

    print(f"\nRun artifacts written to {out_dir}")
    print(f"  junit.xml    - {out_dir / 'junit.xml'}")
    print(f"  coverage.json - {out_dir / 'coverage.json'}")
    return result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent.parent / "replay_data" / "run"))
    parser.add_argument("--variant", default="toolz")
    args = parser.parse_args()
    run_once(Path(args.out_dir), args.variant)


if __name__ == "__main__":
    main()
