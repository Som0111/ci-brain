"""Groups test failures by likely root cause.

## Why not the assertion message text alone

These are pytest `assert` failures, so the traceback's deepest frame is
always *inside the test function*, not inside whatever library code is
actually buggy. Text similarity between messages was tried and measured
empirically (see the calibration script referenced in HUMAN_GUIDE.md): two
failures from the *same* seeded bug (both `merge()`) scored a *lower*
similarity ratio (0.41) than two failures from *different* bugs (0.75),
because dict/defaultdict/custom-object diffs vary wildly in shape even for
identical root causes. Message text alone is not a reliable signal here.

## The two signals actually used

1. **Covered source files**, from Phase 4's dependency graph built off the
   clean baseline. A failing test's root cause is very likely among the
   non-test files it's known to exercise. Verified empirically: this cleanly
   unifies all `merge()`-caused failures under `dicttoolz.py` and all
   `identity()`-caused failures under `functoolz.py`, with zero cross-bug
   mixing for those two.
2. **The innermost function pytest's assertion rewriting captured**, when
   present (`where 1 = first(...)`) - pytest adds this automatically whenever
   the compared value came from a call expression, and when it's there it's
   the single strongest signal available, precise enough to split two bugs
   that live in the *same* file.

## Known, tested limitation

`itertoolz.py` in this project's seeded benchmark carries two independent
bugs (`unique`, `first`). Failures that lack a "where" hint (e.g. `unique()`
compared directly rather than through a captured call) fall back to the
file-level grouping and land in one cluster together, mixing the two bugs.
This is a real limitation of a heuristic approach, not a bug worth chasing
further here - see `tests/test_clustering.py` for what does and doesn't
separate, and HUMAN_GUIDE.md for the measurement that led to this design.
"""
import re
from dataclasses import dataclass, field

_WHERE_CALL = re.compile(r"where\s+\S+\s*=\s*(?:<function\s+)?([a-zA-Z_]\w*)")


def extract_call_hint(message: str) -> str | None:
    """The innermost function name pytest's assertion rewrite captured, if any.

    pytest nests "where" clauses from innermost to outermost (least indented
    first), e.g. ``where 1 = first(...)`` before ``where ... = interpose(...)``
    - so the first match is the most specific, direct cause.
    """
    matches = _WHERE_CALL.findall(message or "")
    return matches[0] if matches else None


@dataclass
class FailureRecord:
    node_id: str
    file_path: str
    message: str


@dataclass
class FailureCluster:
    key: tuple
    failures: list[FailureRecord] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.failures)

    @property
    def covered_files(self):
        return self.key[0]

    @property
    def call_hint(self) -> str | None:
        return self.key[1]

    @property
    def representative(self) -> FailureRecord:
        """Shortest message in the cluster - the least noise for an LLM prompt."""
        return min(self.failures, key=lambda f: len(f.message))


def fetch_failures(db, repo_id: int, run_id: int | None = None) -> list[FailureRecord]:
    """Failed/errored TestResults for a repo, optionally scoped to one run."""
    from sqlalchemy import select

    from app.models import TestCase, TestResult, TestStatus

    query = (
        select(TestCase.node_id, TestCase.file_path, TestResult.message)
        .join(TestResult, TestResult.test_case_id == TestCase.id)
        .where(TestCase.repo_id == repo_id, TestResult.status.in_([TestStatus.FAILED, TestStatus.ERROR]))
    )
    if run_id is not None:
        query = query.where(TestResult.test_run_id == run_id)

    return [
        FailureRecord(node_id=node_id, file_path=file_path, message=message or "")
        for node_id, file_path, message in db.execute(query).all()
    ]


def cluster_failures(
    failures: list[FailureRecord], test_covered_files: dict[str, frozenset[str]]
) -> list[FailureCluster]:
    """`test_covered_files` maps a test's node_id to the source files it's known
    to cover (from Phase 4's dependency graph, built off passing baseline runs)."""
    clusters: dict[tuple, FailureCluster] = {}
    for f in failures:
        covered = test_covered_files.get(f.node_id, frozenset())
        hint = extract_call_hint(f.message)
        key = (covered, hint)
        clusters.setdefault(key, FailureCluster(key=key)).failures.append(f)
    return sorted(clusters.values(), key=lambda c: -c.size)
