"""Test impact analysis: which tests need to run for a given code change.

## How the "dependency graph" actually works

coverage.py with per-test contexts records, for every source line, which tests
executed it. Aggregated across runs that gives a direct source-file -> tests
mapping. Worth being precise about what that is: it is *not* a multi-hop import
graph we traverse. Coverage observes real execution, so if a test calls
`foo()` which calls `bar()` in another module, coverage already records that
test against lines in *both* files. The transitive closure of runtime
dependencies is therefore already flattened into a single lookup - which is
both why this is accurate for code that ran, and why it is blind to code that
didn't (see conservative fallbacks below).

## Conservative fallbacks (why the runtime savings are not larger)

Selection must never silently drop a test that would have caught the change.
Anywhere the coverage data cannot answer the question, we fall back to the
full suite rather than guess:

- **Config/infra files changed** (conftest.py, pytest.ini, setup.py, ...) can
  affect any test, and coverage says nothing about them.
- **A changed source file absent from the graph** means no recorded test
  executed it. Tempting to select zero tests - but a new or previously-dead
  file can still break every test that imports it (import-time errors, side
  effects), and coverage cannot see that. So: full suite.
- **Coverage contexts we cannot map** (unparseable ids, or ids that match no
  stored TestCase) would silently shrink the selection - the test they name
  would never be run. Any such id in a selected set forces the full suite.
- **No changed files / paths outside the repo** (absolute, ``../`` traversal)
  carry no information, so they also fall back rather than select nothing.
- **Changed test files** always run in full, including tests too new to appear
  in the coverage data at all.
"""
import posixpath
import re
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TestRun

# Changing any of these can affect arbitrary tests; coverage data can't tell us which.
ALWAYS_FULL_SUITE = {
    "conftest.py",
    "pytest.ini",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "tox.ini",
}
ALWAYS_FULL_SUITE_SUFFIXES = ("requirements.txt",)


# Marks a coverage context we could not translate to a stored test id. It never
# matches a TestCase, so `select_tests` sees an unknown id and runs everything.
UNMAPPED_CONTEXT = "<unmapped-context>"

# Third-party / generated trees: coverage edges into these say nothing about repo code.
_VENDOR_PARTS = {"site-packages", "dist-packages", "node_modules", ".venv", "venv", ".tox", "__pycache__"}
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def normalize_path(path: str) -> str:
    """coverage.py emits OS-native separators; git diff always emits POSIX ones.

    Also collapses ``./``, ``//`` and ``a/../b``. Leading ``../`` and absolute
    paths are preserved so `in_repo_path` can reject them.
    """
    path = path.strip().replace("\\", "/")
    return posixpath.normpath(path) if path else path


def in_repo_path(norm: str) -> bool:
    """True for a repo-relative path that stays inside the repo and isn't vendored."""
    if not norm or norm.startswith("/") or _DRIVE_RE.match(norm) or norm == "." or "\x00" in norm:
        return False
    parts = norm.split("/")
    return ".." not in parts and not (_VENDOR_PARTS & set(parts))


@lru_cache(maxsize=200_000)  # pure function; the same contexts repeat across lines, files and runs
def normalize_test_id(context: str) -> str:
    """Convert a coverage context id to the same form the ingestion API stores.

    coverage/pytest: ``toolz/tests/test_dicttoolz.py::TestDict::test_merge``
    stored (JUnit):  ``toolz.tests.test_dicttoolz.TestDict::test_merge``

    Both identify the same test; JUnit XML just reports the module path in
    dotted form with the class folded in. Without this the graph's test ids
    would never join against the TestCase rows.
    """
    context = context.replace("\\", "/").split("|", 1)[0]  # drop pytest-cov's |setup/|run/|teardown
    parts = context.split("::")
    module = parts[0].removesuffix(".py").replace("/", ".")
    rest = parts[1:]
    if not rest:
        return module
    if len(rest) == 1:
        return f"{module}::{rest[0]}"
    return f"{module}.{'.'.join(rest[:-1])}::{rest[-1]}"


def to_pytest_nodeid(node_id: str, file_path: str) -> str:
    """Inverse of `normalize_test_id`: stored id + file path -> runnable pytest id.

    ``toolz.tests.test_dicttoolz.TestDict::test_merge`` + ``toolz/tests/test_dicttoolz.py``
    -> ``toolz/tests/test_dicttoolz.py::TestDict::test_merge``
    """
    file_path = normalize_path(file_path)
    classname, _, test_name = node_id.rpartition("::")
    module_dotted = file_path.removesuffix(".py").replace("/", ".")
    class_suffix = classname.removeprefix(module_dotted).lstrip(".")
    parts = [file_path] + ([class_suffix] if class_suffix else []) + [test_name]
    return "::".join(parts)


def is_test_file(path: str) -> bool:
    base = posixpath.basename(normalize_path(path))
    return base.startswith("test_") or base.endswith("_test.py")


def forces_full_suite(path: str) -> bool:
    norm = normalize_path(path)
    base = posixpath.basename(norm)
    return base in ALWAYS_FULL_SUITE or norm.endswith(ALWAYS_FULL_SUITE_SUFFIXES)


@lru_cache(maxsize=200_000)
def _map_context(ctx: str) -> str:
    return normalize_test_id(ctx) if _parseable_context(ctx) else UNMAPPED_CONTEXT


def _parseable_context(ctx: str) -> bool:
    """A pytest context looks like ``path/to/test_x.py::[Class::]test_name[|phase]``."""
    parts = ctx.replace("\\", "/").split("|", 1)[0].split("::")
    return len(parts) >= 2 and all(parts) and parts[0].endswith(".py")


def build_file_test_map(coverage_data: dict) -> dict[str, set[str]]:
    """One run's coverage JSON -> {source file: tests that executed a line in it}."""
    file_test_map: dict[str, set[str]] = {}

    for file_path, file_data in coverage_data.get("files", {}).items():
        tests: set[str] = set()
        for contexts in file_data.get("contexts", {}).values():
            for ctx in contexts:
                if not ctx:
                    continue  # empty context = collection-time execution, not a real test
                tests.add(_map_context(ctx))
        norm = normalize_path(file_path)
        if tests and in_repo_path(norm):
            file_test_map[norm] = tests

    return file_test_map


def build_dependency_graph(db: Session, repo_id: int, commit_sha: str | None = None) -> dict[str, set[str]]:
    """Union the file-to-test maps of every stored run for a repo.

    Unioning (rather than taking the latest run) matters because a flaky or
    early-exiting run can miss edges; a test that touched a file in *any*
    observed run is a real dependency.
    """
    # Select just the (deferred, possibly huge) JSON column and stream it a few rows at a time, so memory
    # holds one run's coverage rather than all of them.
    query = select(TestRun.coverage_data).where(TestRun.repo_id == repo_id)
    if commit_sha is not None:
        query = query.where(TestRun.commit_sha == commit_sha)

    graph: dict[str, set[str]] = {}
    for coverage_data in db.scalars(query.execution_options(yield_per=5)):
        if not coverage_data:
            continue
        for file_path, tests in build_file_test_map(coverage_data).items():
            graph.setdefault(file_path, set()).update(tests)
    return graph


def get_all_tests(db: Session, repo_id: int) -> set[str]:
    from app.models import TestCase

    return set(db.scalars(select(TestCase.node_id).where(TestCase.repo_id == repo_id)).all())


def get_tests_by_file(db: Session, repo_id: int) -> dict[str, set[str]]:
    """Test file -> tests defined in it, from stored results.

    Sourced from `TestCase.file_path` rather than coverage, so it includes
    tests that execute no measured source lines and therefore never appear in
    the coverage graph at all.
    """
    from app.models import TestCase

    by_file: dict[str, set[str]] = {}
    rows = db.execute(select(TestCase.file_path, TestCase.node_id).where(TestCase.repo_id == repo_id))
    for file_path, node_id in rows:
        by_file.setdefault(normalize_path(file_path), set()).add(node_id)
    return by_file


@dataclass
class SelectionResult:
    selected: set[str] = field(default_factory=set)
    full_suite_fallback: bool = False
    reasons: list[str] = field(default_factory=list)
    unknown_files: list[str] = field(default_factory=list)

    @property
    def selected_count(self) -> int:
        return len(self.selected)


def select_tests(
    changed_files: list[str],
    graph: dict[str, set[str]],
    all_tests: set[str],
    tests_by_file: dict[str, set[str]] | None = None,
) -> SelectionResult:
    """Pick the minimal test subset for `changed_files`, erring toward safety.

    `tests_by_file` maps a *test file* path to the tests defined in it, so a
    changed test file runs all of its own tests (coverage alone would only
    show tests that happened to execute lines in that file).
    """
    result = SelectionResult()
    tests_by_file = tests_by_file or {}

    if not changed_files:
        # Selecting nothing would read as "safe to run nothing" - never infer that from no input.
        result.full_suite_fallback = True
        result.reasons.append("no changed files given, cannot determine impact")

    for path in changed_files:
        norm = normalize_path(path)

        if not in_repo_path(norm):
            result.unknown_files.append(norm)
            result.full_suite_fallback = True
            result.reasons.append(f"{norm}: outside repo / vendored / absolute path, impact unknown")
            continue

        if forces_full_suite(norm):
            result.full_suite_fallback = True
            result.reasons.append(f"{norm}: config/infra file, can affect any test")
            continue

        if is_test_file(norm):
            own = tests_by_file.get(norm, set())
            if own:
                result.selected |= own
                result.reasons.append(f"{norm}: changed test file, running its {len(own)} test(s)")
            else:
                # A test file we've never recorded results for - most likely brand new.
                result.full_suite_fallback = True
                result.reasons.append(f"{norm}: test file with no recorded tests (new?), cannot enumerate")
            continue

        if norm in graph:
            hit = graph[norm]
            if not hit <= all_tests:
                result.full_suite_fallback = True
                result.reasons.append(f"{norm}: coverage names tests with no stored match, mapping unreliable")
            result.selected |= hit
            result.reasons.append(f"{norm}: {len(hit)} test(s) cover this file")
        else:
            result.unknown_files.append(norm)
            result.full_suite_fallback = True
            result.reasons.append(f"{norm}: no coverage data, impact unknown")

    if result.full_suite_fallback:
        result.selected = set(all_tests)

    return result
