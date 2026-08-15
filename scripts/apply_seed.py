"""
Copy a tracked seed file (synthetic flaky tests, synthetic bugs) into a
cloned target repo variant.

Kept as an explicit, separate step from clone_target.py so the seed source
lives in version control (`seeds/`) rather than only existing as a hand-edit
inside a gitignored clone under `target_repos/` - re-running clone_target.py
alone would otherwise silently drop the seeding on a fresh clone.
"""
import argparse
import shutil
from pathlib import Path

from scripts.clone_target import target_dir

SEEDS_ROOT = Path(__file__).resolve().parent.parent / "seeds"


def apply_seed(variant: str, seed_file: Path, dest_relative: str) -> Path:
    dest = target_dir(variant) / dest_relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_file, dest)
    return dest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, help="target_repos/ subdirectory to seed")
    parser.add_argument("--seed-file", required=True, help="path under seeds/, e.g. flaky/test_seeded_flaky.py")
    parser.add_argument(
        "--dest",
        required=True,
        help="path relative to the target repo root to copy the seed to, "
        "e.g. toolz/tests/test_seeded_flaky.py",
    )
    args = parser.parse_args()

    seed_file = Path(args.seed_file)
    if not seed_file.is_absolute():
        seed_file = SEEDS_ROOT / args.seed_file

    dest = apply_seed(args.variant, seed_file, args.dest)
    print(f"Applied seed {seed_file} -> {dest}")


if __name__ == "__main__":
    main()
