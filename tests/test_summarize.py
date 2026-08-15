import pytest

from app.analysis.clustering import FailureCluster, FailureRecord
from app.analysis.summarize import SummarizerNotConfigured, build_prompt, summarize_cluster


def test_build_prompt_includes_files_and_representative_message():
    cluster = FailureCluster(
        key=(frozenset({"toolz/dicttoolz.py"}), None),
        failures=[FailureRecord("m::test_merge", "m.py", "assert {} == {1: 1}")],
    )
    prompt = build_prompt(cluster)
    assert "toolz/dicttoolz.py" in prompt
    assert "m::test_merge" in prompt
    assert "assert {} == {1: 1}" in prompt
    assert "1 test(s) failed" in prompt


def test_build_prompt_includes_call_hint_when_present():
    cluster = FailureCluster(
        key=(frozenset({"toolz/functoolz.py"}), "identity"),
        failures=[FailureRecord("m::test_compose", "m.py", "assert None == 0")],
    )
    prompt = build_prompt(cluster)
    assert "identity()" in prompt


def test_build_prompt_omits_hint_line_when_absent():
    cluster = FailureCluster(
        key=(frozenset({"a.py"}), None),
        failures=[FailureRecord("m::test_x", "m.py", "assert 1 == 2")],
    )
    prompt = build_prompt(cluster)
    assert "pytest identified" not in prompt


def test_build_prompt_lists_other_tests_in_cluster():
    cluster = FailureCluster(
        key=(frozenset({"a.py"}), None),
        failures=[
            FailureRecord("m::test_a", "m.py", "shortest"),
            FailureRecord("m::test_b", "m.py", "a longer message here"),
        ],
    )
    prompt = build_prompt(cluster)
    # representative = shortest message (test_a), test_b should appear in "other tests"
    assert "m::test_a" in prompt
    assert "Other tests in this cluster: m::test_b" in prompt


def test_build_prompt_handles_no_other_tests():
    cluster = FailureCluster(
        key=(frozenset({"a.py"}), None),
        failures=[FailureRecord("m::test_solo", "m.py", "assert 1 == 2")],
    )
    prompt = build_prompt(cluster)
    assert "(none)" in prompt


def test_summarize_cluster_without_key_raises_clean_error(monkeypatch):
    from app.analysis import summarize

    monkeypatch.setattr(summarize.settings, "gemini_api_key", None)
    cluster = FailureCluster(key=(frozenset(), None), failures=[FailureRecord("m::x", "m.py", "e")])

    with pytest.raises(SummarizerNotConfigured):
        summarize_cluster(cluster)
