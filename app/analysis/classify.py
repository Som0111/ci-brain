"""Classifies per-test variance stats (from flakiness.py) into verdicts.

Threshold design rationale (Phase 3 decision):
- Flakiness is defined as *both* outcomes observed on identical code, not as a
  fail-rate percentage band. A 5% fail rate is still flaky; a 100% fail rate
  is not flaky, it's a consistently broken test.
- Confidence comes from the minority-outcome count (how many times the rarer
  outcome was seen), which is what actually measures evidence strength at
  small sample sizes: 1 flip could be a fluke, 3+ flips cannot reasonably be.
- Below MIN_RUNS non-skip runs we refuse to classify rather than guess.

What the labels mean (they are heuristics, not calibrated probabilities - no
significance test or p-value is computed):
- HIGH / MEDIUM / LOW = the rarer outcome was seen >=3 / exactly 2 / exactly 1
  times among the non-skipped runs. It says how much evidence there is that
  both outcomes really occur, not how likely a given run is to fail.
- `quarantine` = FLAKY with HIGH or MEDIUM confidence.
- Skipped results never count as a pass or a fail; 'error' counts as a fail.
- Inputs are only trustworthy when all runs share one commit (see the API's
  `commit_sha` filter / `warning`) and are not duplicate uploads (`run_key`).
"""
import enum
from dataclasses import dataclass

from app.analysis.flakiness import TestVarianceStats

MIN_RUNS = 5


class Verdict(str, enum.Enum):
    STABLE = "stable"
    FLAKY = "flaky"
    CONSISTENTLY_FAILING = "consistently_failing"
    INSUFFICIENT_DATA = "insufficient_data"


class Confidence(str, enum.Enum):
    HIGH = "high"      # minority outcome seen >= 3 times
    MEDIUM = "medium"  # seen twice
    LOW = "low"        # seen once


@dataclass
class Classification:
    stats: TestVarianceStats
    verdict: Verdict
    confidence: Confidence | None  # only set for FLAKY
    quarantine: bool  # recommend quarantining (flaky at medium+ confidence)


def classify(stats: TestVarianceStats) -> Classification:
    if stats.non_skip_runs < MIN_RUNS:
        return Classification(stats, Verdict.INSUFFICIENT_DATA, None, False)

    if not stats.is_inconsistent:
        verdict = Verdict.CONSISTENTLY_FAILING if stats.fail_count > 0 else Verdict.STABLE
        return Classification(stats, verdict, None, False)

    minority = min(stats.pass_count, stats.fail_count)
    if minority >= 3:
        confidence = Confidence.HIGH
    elif minority == 2:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    quarantine = confidence in (Confidence.HIGH, Confidence.MEDIUM)
    return Classification(stats, Verdict.FLAKY, confidence, quarantine)


def classify_all(all_stats: list[TestVarianceStats]) -> list[Classification]:
    return [classify(s) for s in all_stats]
