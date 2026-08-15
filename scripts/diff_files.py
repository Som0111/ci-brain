"""Compute the set of files changed between two commits in a target repo variant."""
import argparse
import subprocess

from scripts.clone_target import target_dir


def changed_files(variant: str, base: str, head: str) -> list[str]:
    """Files differing between `base` and `head` (git already emits POSIX paths)."""
    out = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        cwd=target_dir(variant),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def changed_files_working_tree(variant: str) -> list[str]:
    """Files modified in the working tree vs HEAD, including untracked ones.

    Used by the benchmark harness, which applies a change to the checkout
    directly rather than committing it.
    """
    tdir = target_dir(variant)
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"], cwd=tdir, capture_output=True, text=True, check=True
    ).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=tdir, capture_output=True, text=True, check=True,
    ).stdout
    return sorted({line.strip() for line in (tracked + untracked).splitlines() if line.strip()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="toolz")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    for f in changed_files(args.variant, args.base, args.head):
        print(f)


if __name__ == "__main__":
    main()
