"""Empirically verify that impact selection never drops a test that would
have caught a change.

For each scenario: break one source file, run the FULL suite, collect the
tests that actually failed, and assert that set is a subset of what impact
selection would have chosen for that file. A selection that misses even one
genuinely-failing test is unsafe, no matter how good its reduction number
looks - so this is the check that has to pass before any benchmark number
from Phase 4 means anything.

The break is injected by appending a redefinition at module end (Python
rebinds the name), which works for any pure-Python module without needing to
understand its internals.
"""
import argparse
import subprocess
from pathlib import Path

from app.analysis.impact import (
    build_dependency_graph,
    get_all_tests,
    get_tests_by_file,
    select_tests,
)
from app.database import SessionLocal
from app.parsers.junit import parse_junit_xml
from scripts.clone_target import target_dir
from scripts.run_target_tests import run_once

# (source file, code appended to break it)
SCENARIOS = [
    ("toolz/dicttoolz.py", "\n\ndef merge(*dicts, **kwargs):  # INJECTED BREAKAGE\n    return {}\n"),
    ("toolz/itertoolz.py", "\n\ndef groupby(key, seq):  # INJECTED BREAKAGE\n    return {}\n"),
    ("toolz/functoolz.py", "\n\ndef identity(x):  # INJECTED BREAKAGE\n    return None\n"),
]


def failing_tests(out_dir: Path, variant: str) -> set[str]:
    run_once(out_dir, variant)
    parsed = parse_junit_xml((out_dir / "junit.xml").read_bytes())
    return {r.node_id for r in parsed if r.status in ("failed", "error")}


def restore(variant: str, path: str) -> None:
    subprocess.run(["git", "checkout", "--", path], cwd=target_dir(variant), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="toolz")
    parser.add_argument("--repo-id", type=int, default=1)
    parser.add_argument("--out-dir", default="replay_data/verify")
    args = parser.parse_args()

    db = SessionLocal()
    graph = build_dependency_graph(db, args.repo_id)
    all_tests = get_all_tests(db, args.repo_id)
    tests_by_file = get_tests_by_file(db, args.repo_id)
    db.close()

    tdir = target_dir(args.variant)
    all_ok = True

    for source_file, breakage in SCENARIOS:
        selection = select_tests([source_file], graph, all_tests, tests_by_file)

        target_file = tdir / source_file
        original = target_file.read_text(encoding="utf-8")
        try:
            target_file.write_text(original + breakage, encoding="utf-8")
            failed = failing_tests(Path(args.out_dir), args.variant)
        finally:
            target_file.write_text(original, encoding="utf-8")
            restore(args.variant, source_file)

        missed = failed - selection.selected
        ok = not missed
        all_ok &= ok

        print(f"\n=== {source_file} ===")
        print(f"  selected by impact analysis : {selection.selected_count}/{len(all_tests)}")
        print(f"  actually failed (full suite): {len(failed)}")
        print(f"  MISSED by selection         : {len(missed)}  {'OK' if ok else 'UNSAFE'}")
        for m in sorted(missed)[:10]:
            print(f"      MISS {m}")

    print("\nRESULT:", "all scenarios safe" if all_ok else "UNSAFE - selection dropped real failures")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
