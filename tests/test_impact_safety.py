"""Safety invariant: uncertainty must never silently shrink the selected set."""

import pytest

from app.analysis.impact import (
    UNMAPPED_CONTEXT,
    build_file_test_map,
    in_repo_path,
    normalize_path,
    normalize_test_id,
    select_tests,
)

ALL = {"pkg.tests.test_a::test_x", "pkg.tests.test_b::test_y"}
GRAPH = {"pkg/mod.py": {"pkg.tests.test_a::test_x"}}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("./pkg/mod.py", "pkg/mod.py"),
        ("pkg\\sub\\mod.py", "pkg/sub/mod.py"),
        ("pkg//mod.py", "pkg/mod.py"),
        ("pkg/x/../mod.py", "pkg/mod.py"),
        ("  pkg/mod.py ", "pkg/mod.py"),
    ],
)
def test_normalize_path_forms(raw, expected):
    assert normalize_path(raw) == expected


OUTSIDE = [
    "/etc/passwd",
    "C:\\repo\\mod.py",
    "C:/repo/mod.py",
    "../outside.py",
    "a/../../b.py",
    "",
    ".",
    "venv/lib/x.py",
    "x/site-packages/y.py",
    "node_modules/a.js",
]


@pytest.mark.parametrize("path", OUTSIDE)
def test_paths_outside_repo_rejected(path):
    assert not in_repo_path(normalize_path(path))


@pytest.mark.parametrize("path", [p for p in OUTSIDE if p not in ("", ".")])
def test_hostile_changed_path_falls_back_to_full_suite(path):
    r = select_tests([path], GRAPH, ALL)
    assert r.full_suite_fallback and r.selected == ALL


def test_traversal_path_does_not_alias_a_real_graph_edge():
    # "../pkg/mod.py" must not be resolved to "pkg/mod.py"
    assert select_tests(["../pkg/mod.py"], GRAPH, ALL).full_suite_fallback


def test_coverage_edges_for_external_files_are_dropped():
    ctx = {"1": ["a.py::t|run"]}
    data = {
        "files": {
            "/usr/lib/python3/site-packages/x.py": {"contexts": ctx},
            "../other/y.py": {"contexts": ctx},
            "C:\\abs\\z.py": {"contexts": ctx},
            "pkg/ok.py": {"contexts": ctx},
        }
    }
    assert list(build_file_test_map(data)) == ["pkg/ok.py"]


@pytest.mark.parametrize(
    "ctx,expected",
    [
        ("tests/test_a.py::test_f|setup", "tests.test_a::test_f"),
        ("tests/test_a.py::test_f|teardown", "tests.test_a::test_f"),
        ("tests/test_a.py::Outer::Inner::test_f|run", "tests.test_a.Outer.Inner::test_f"),
        ("tests\\sub\\test_a.py::TestC::test_f[1-a]|run", "tests.sub.test_a.TestC::test_f[1-a]"),
        ("pkg/sub/tests/test_a.py::test_f[1]", "pkg.sub.tests.test_a::test_f[1]"),
    ],
)
def test_context_mapping_shapes(ctx, expected):
    assert normalize_test_id(ctx) == expected


@pytest.mark.parametrize("ctx", ["garbage", "test_f", "a.py::", "::test_f", "notpy::test_f"])
def test_unparseable_context_becomes_unmapped_marker(ctx):
    data = {"files": {"pkg/mod.py": {"contexts": {"1": [ctx]}}}}
    assert build_file_test_map(data) == {"pkg/mod.py": {UNMAPPED_CONTEXT}}


def test_unmapped_context_forces_full_suite_not_a_shrunk_selection():
    graph = {"pkg/mod.py": {UNMAPPED_CONTEXT, "pkg.tests.test_a::test_x"}}
    r = select_tests(["pkg/mod.py"], graph, ALL)
    assert r.full_suite_fallback and r.selected == ALL


def test_graph_test_unknown_to_stored_tests_forces_full_suite():
    graph = {"pkg/mod.py": {"pkg.tests.test_zzz::renamed"}}
    r = select_tests(["pkg/mod.py"], graph, ALL)
    assert r.full_suite_fallback and r.selected == ALL


def test_mixed_known_and_unknown_files_run_everything():
    r = select_tests(["pkg/mod.py", "brand_new.py"], GRAPH, ALL)
    assert r.full_suite_fallback and r.selected == ALL and r.unknown_files == ["brand_new.py"]


def test_changed_test_file_alone_does_not_fall_back_but_config_does():
    tbf = {"pkg/tests/test_a.py": {"pkg.tests.test_a::test_x"}}
    r = select_tests(["pkg/tests/test_a.py"], GRAPH, ALL, tbf)
    assert not r.full_suite_fallback and r.selected == {"pkg.tests.test_a::test_x"}
    assert select_tests(["pkg/tests/test_a.py", "tox.ini"], GRAPH, ALL, tbf).selected == ALL


@pytest.mark.parametrize("changed", [[], ["x.py"], ["/abs.py"], ["tox.ini"]])
def test_no_evidence_never_selects_a_subset(changed):
    r = select_tests(changed, {}, ALL)
    assert r.selected == ALL and r.full_suite_fallback
