"""
SEEDED SYNTHETIC FLAKY TESTS — intentionally introduced for CI Brain Phase 3
benchmarking (flakiness detection). These are NOT real bugs in toolz and do
not exercise toolz's own logic; do not treat failures here as toolz defects.
Each test is deliberately written to pass/fail inconsistently across
independent `pytest` process runs, without needing pytest-randomly: Python
randomizes hash seeds and real wall-clock timing naturally differs per
process, which is enough to make these non-deterministic.
"""
import hashlib
import random
import threading
import time


def test_flaky_unseeded_random():
    """Coin flip on the wall-clock-seeded default random state. ~50% fail rate."""
    assert random.random() < 0.5


def test_flaky_sleep_race():
    """Sleep-based race: the worker's delay is randomized around the check
    point, so whether it's "done" by the time we check is a genuine
    per-process coin flip rather than something OS timing always resolves
    the same way on a fast/idle machine."""
    result = {}

    def worker(delay):
        time.sleep(delay)
        result["done"] = True

    threading.Thread(target=worker, args=(random.uniform(0, 0.002),)).start()
    time.sleep(0.001)
    assert result.get("done") is True


def test_flaky_hash_randomization_order():
    """Set iteration order depends on PYTHONHASHSEED, which Python randomizes
    per process by default. Fails whenever this run's hash seed doesn't
    happen to order these three strings alphabetically."""
    s = {"banana", "apple", "cherry"}
    assert list(s) == sorted(s)


def test_flaky_tight_timing_budget():
    """Work whose size is randomized per process, so the tight time budget
    is a genuine coin flip rather than something that (almost) always
    resolves the same way based on how fast/idle the machine happens to be."""
    size = random.randint(40_000, 180_000)
    start = time.perf_counter()
    hashlib.sha256(b"x" * size).hexdigest()
    elapsed = time.perf_counter() - start
    assert elapsed < 0.0004
