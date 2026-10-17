"""Every tracked script must import cleanly and (if it has a CLI) answer --help with exit code 0.

Note: the checklist names scripts/seed_test_data.py, which does not exist; scripts/apply_seed.py is the seeding
script. Scratch scripts (leading underscore) are skipped.
"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
ROOT = SCRIPTS_DIR.parent
MODULES = sorted(p.stem for p in SCRIPTS_DIR.glob("*.py") if not p.name.startswith("_"))
CLI_MODULES = [m for m in MODULES if "argparse" in (SCRIPTS_DIR / f"{m}.py").read_text(encoding="utf-8")]


def test_expected_scripts_are_present():
    assert {"apply_seed", "benchmark_impact", "verify_selection", "replay_harness"} <= set(MODULES)


@pytest.mark.parametrize("module", MODULES)
def test_script_imports_without_side_effects(module):
    importlib.import_module(f"scripts.{module}")


@pytest.mark.parametrize("module", CLI_MODULES)
def test_cli_help_exits_zero(module):
    proc = subprocess.run(
        [sys.executable, "-m", f"scripts.{module}", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage" in proc.stdout.lower()


def test_benchmark_and_verify_cover_the_same_files():
    from scripts.benchmark_impact import SCENARIOS as BENCH
    from scripts.verify_selection import SCENARIOS as VERIFY

    assert set(BENCH) == {path for path, _ in VERIFY}, "every benchmarked file must also be failure-injected"
