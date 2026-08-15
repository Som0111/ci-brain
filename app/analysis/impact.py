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
- **Changed test files** always run in full, including tests too new to appear
  in the coverage data at all.
"""
import posixpath
from dataclasses import dataclass, field

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


def normalize_path(path: str) -> str:
    """coverage.py emits OS-native separators; git diff always emits POSIX ones."""
    return path.replace("\\", "/")


def normalize_test_id(context: str) -> str:
    """Convert a coverage context id to the same form the ingestion API stores.

    coverage/pytest: ``toolz/tests/test_dicttoolz.py::TestDict::test_merge``
    stored (JUnit):  ``toolz.tests.test_dicttoolz.TestDict::test_merge``

    Both identify the same test; JUnit XML just reports the module path in
    dotted form with the class folded in. Without this the graph's test ids
    would never join against the TestCase rows.
    """
    context = normalize_path(context).split("|", 1)[0]  # drop pytest-cov's |setup/|run/|teardown
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


def build_file_test_map(coverage_data: dict) -> dict[str, set[str]]:
    """One run's coverage JSON -> {source file: tests that executed a line in it}."""
    file_test_map: dict[str, set[str]] = {}

    for file_path, file_data in coverage_data.get("files", {}).items():
        tests: set[str] = set()
        for contexts in file_data.get("contexts", {}).values():
            for ctx in contexts:
                if not ctx:
                    continue  # empty context = collection-time execution, not a real test
                tests.add(normalize_test_id(ctx))
        if tests:
            file_test_map[normalize_path(file_path)] = tests

    return file_test_map


def build_dependency_graph(db: Session, repo_id: int, commit_sha: str | None = None) -> dict[str, set[str]]:
    """Union the file-to-test maps of every stored run for a repo.

    Unioning (rather than taking the latest run) matters because a flaky or
    early-exiting run can miss edges; a test that touched a file in *any*
    observed run is a real dependency.
    """
    query = select(TestRun).where(TestRun.repo_id == repo_id)
    if commit_sha is not None:
        query = query.where(TestRun.commit_sha == commit_sha)

    graph: dict[str, set[str]] = {}
    for run in db.scalars(query).all():
        if not run.coverage_data:
            continue
        for file_path, tests in build_file_test_map(run.coverage_data).items():
            graph.setdefault(file_path, set()).update(tests)
    return graph


def get_all_tests(db: Session, repo_id: int) -> set[str]:
    from app.models import TestCase

    return {tc.node_id for tc in db.scalars(select(TestCase).where(TestCase.repo_id == repo_id)).all()}


def get_tests_by_file(db: Session, repo_id: int) -> dict[str, set[str]]:
    """Test file -> tests defined in it, from stored results.

    Sourced from `TestCase.file_path` rather than coverage, so it includes
    tests that execute no measured source lines and therefore never appear in
    the coverage graph at all.
    """
    from app.models import TestCase

    by_file: dict[str, set[str]] = {}
    for tc in db.scalars(select(TestCase).where(TestCase.repo_id == repo_id)).all():
        by_file.setdefault(normalize_path(tc.file_path), set()).add(tc.node_id)
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
        result.reasons.append("no files changed")
        return result

    for path in changed_files:
        norm = normalize_path(path)

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
            result.selected |= hit
            result.reasons.append(f"{norm}: {len(hit)} test(s) cover this file")
        else:
            result.unknown_files.append(norm)
            result.full_suite_fallback = True
            result.reasons.append(f"{norm}: no coverage data, impact unknown")

    if result.full_suite_fallback:
        result.selected = set(all_tests)

    return result
