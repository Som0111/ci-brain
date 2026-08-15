from app.analysis.classify import MIN_RUNS, Confidence, Verdict, classify
from app.analysis.flakiness import TestVarianceStats


def _stats(passed=0, failed=0, skipped=0):
    return TestVarianceStats(node_id="t", file_path="t.py",
                             pass_count=passed, fail_count=failed, skip_count=skipped)


def test_stable_test():
    c = classify(_stats(passed=20))
    assert c.verdict is Verdict.STABLE
    assert c.quarantine is False


def test_flaky_high_confidence_even_split():
    c = classify(_stats(passed=10, failed=10))
    assert c.verdict is Verdict.FLAKY
    assert c.confidence is Confidence.HIGH
    assert c.quarantine is True


def test_flaky_low_rate_still_flagged():
    # 1 fail in 20 runs is still flaky, but weak evidence -> low, no quarantine
    c = classify(_stats(passed=19, failed=1))
    assert c.verdict is Verdict.FLAKY
    assert c.confidence is Confidence.LOW
    assert c.quarantine is False


def test_flaky_medium_confidence():
    # 90% failer with 2 passes: flaky, medium confidence, quarantined
    c = classify(_stats(passed=2, failed=18))
    assert c.verdict is Verdict.FLAKY
    assert c.confidence is Confidence.MEDIUM
    assert c.quarantine is True


def test_always_failing_is_not_flaky():
    c = classify(_stats(failed=20))
    assert c.verdict is Verdict.CONSISTENTLY_FAILING
    assert c.quarantine is False


def test_insufficient_data_guard():
    c = classify(_stats(passed=2, failed=2))  # 4 runs < MIN_RUNS
    assert c.verdict is Verdict.INSUFFICIENT_DATA
    assert c.quarantine is False


def test_skips_dont_count_toward_min_runs():
    c = classify(_stats(passed=3, failed=1, skipped=10))
    assert c.verdict is Verdict.INSUFFICIENT_DATA


def test_min_runs_boundary():
    c = classify(_stats(passed=4, failed=1))  # exactly MIN_RUNS non-skip runs
    assert MIN_RUNS == 5
    assert c.verdict is Verdict.FLAKY
    assert c.confidence is Confidence.LOW
