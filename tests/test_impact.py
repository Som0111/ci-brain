from app.analysis.impact import (
    build_file_test_map,
    is_test_file,
    normalize_test_id,
    select_tests,
)

GRAPH = {
    "toolz/dicttoolz.py": {"toolz.tests.test_dicttoolz::test_merge", "toolz.tests.test_curried::test_merge"},
    "toolz/itertoolz.py": {"toolz.tests.test_itertoolz::test_groupby"},
}
ALL_TESTS = {
    "toolz.tests.test_dicttoolz::test_merge",
    "toolz.tests.test_curried::test_merge",
    "toolz.tests.test_itertoolz::test_groupby",
    "toolz.tests.test_utils::test_raises",
}
TESTS_BY_FILE = {
    "toolz/tests/test_dicttoolz.py": {"toolz.tests.test_dicttoolz::test_merge"},
    "toolz/tests/test_itertoolz.py": {"toolz.tests.test_itertoolz::test_groupby"},
    "toolz/tests/test_utils.py": {"toolz.tests.test_utils::test_raises"},
}


class TestNormalizeTestId:
    def test_module_level_test(self):
        assert normalize_test_id("toolz/tests/test_utils.py::test_raises") == "toolz.tests.test_utils::test_raises"

    def test_class_based_test(self):
        assert (
            normalize_test_id("toolz/tests/test_dicttoolz.py::TestDict::test_merge")
            == "toolz.tests.test_dicttoolz.TestDict::test_merge"
        )

    def test_strips_pytest_cov_phase_suffix(self):
        assert normalize_test_id("toolz/tests/test_utils.py::test_raises|run") == "toolz.tests.test_utils::test_raises"

    def test_handles_windows_separators(self):
        assert normalize_test_id("toolz\\tests\\test_utils.py::test_raises") == "toolz.tests.test_utils::test_raises"

    def test_parametrized_test_keeps_params(self):
        assert (
            normalize_test_id("toolz/tests/test_x.py::test_add[1-2]") == "toolz.tests.test_x::test_add[1-2]"
        )


class TestBuildFileTestMap:
    def test_maps_and_normalizes(self):
        data = {
            "files": {
                "toolz\\dicttoolz.py": {
                    "contexts": {"12": ["", "toolz/tests/test_dicttoolz.py::TestDict::test_merge|run"]}
                }
            }
        }
        result = build_file_test_map(data)
        assert result == {"toolz/dicttoolz.py": {"toolz.tests.test_dicttoolz.TestDict::test_merge"}}

    def test_file_hit_only_at_collection_time_is_excluded(self):
        data = {"files": {"toolz/utils.py": {"contexts": {"1": [""]}}}}
        assert build_file_test_map(data) == {}


class TestSelection:
    def test_single_source_file_selects_covering_tests(self):
        r = select_tests(["toolz/dicttoolz.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.selected == GRAPH["toolz/dicttoolz.py"]
        assert r.full_suite_fallback is False
        assert r.selected_count < len(ALL_TESTS)

    def test_multiple_files_union(self):
        r = select_tests(["toolz/dicttoolz.py", "toolz/itertoolz.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.selected == GRAPH["toolz/dicttoolz.py"] | GRAPH["toolz/itertoolz.py"]

    def test_no_changes_selects_nothing(self):
        r = select_tests([], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.selected == set()
        assert r.full_suite_fallback is False

    def test_changed_test_file_runs_its_own_tests(self):
        r = select_tests(["toolz/tests/test_utils.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        # test_utils has no coverage edges at all, but its own test must still run
        assert r.selected == {"toolz.tests.test_utils::test_raises"}
        assert r.full_suite_fallback is False

    def test_unknown_test_file_falls_back_to_full_suite(self):
        r = select_tests(["toolz/tests/test_brand_new.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.full_suite_fallback is True
        assert r.selected == ALL_TESTS

    def test_conftest_forces_full_suite(self):
        r = select_tests(["conftest.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.full_suite_fallback is True
        assert r.selected == ALL_TESTS

    def test_requirements_change_forces_full_suite(self):
        r = select_tests(["requirements.txt"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.full_suite_fallback is True

    def test_uncovered_source_file_falls_back_rather_than_selecting_nothing(self):
        r = select_tests(["toolz/brand_new_module.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.full_suite_fallback is True
        assert r.unknown_files == ["toolz/brand_new_module.py"]
        assert r.selected == ALL_TESTS

    def test_whole_file_rewrite_is_same_as_any_change(self):
        # selection is path-based, so the size of the edit is irrelevant
        r = select_tests(["toolz/itertoolz.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.selected == GRAPH["toolz/itertoolz.py"]

    def test_windows_paths_normalize(self):
        r = select_tests(["toolz\\dicttoolz.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.selected == GRAPH["toolz/dicttoolz.py"]

    def test_one_unknown_file_forces_full_suite_even_alongside_known(self):
        r = select_tests(["toolz/dicttoolz.py", "toolz/mystery.py"], GRAPH, ALL_TESTS, TESTS_BY_FILE)
        assert r.full_suite_fallback is True
        assert r.selected == ALL_TESTS


class TestIsTestFile:
    def test_recognizes_test_prefix_and_suffix(self):
        assert is_test_file("toolz/tests/test_x.py")
        assert is_test_file("pkg/x_test.py")

    def test_source_file_is_not_a_test_file(self):
        assert not is_test_file("toolz/dicttoolz.py")


class TestToPytestNodeId:
    def test_module_level_round_trip(self):
        from app.analysis.impact import to_pytest_nodeid

        assert (
            to_pytest_nodeid("toolz.tests.test_utils::test_raises", "toolz/tests/test_utils.py")
            == "toolz/tests/test_utils.py::test_raises"
        )

    def test_class_based_round_trip(self):
        from app.analysis.impact import to_pytest_nodeid

        assert (
            to_pytest_nodeid(
                "toolz.tests.test_dicttoolz.TestDict::test_merge", "toolz/tests/test_dicttoolz.py"
            )
            == "toolz/tests/test_dicttoolz.py::TestDict::test_merge"
        )

    def test_inverts_normalize_test_id(self):
        from app.analysis.impact import normalize_test_id, to_pytest_nodeid

        original = "toolz/tests/test_dicttoolz.py::TestDict::test_merge"
        stored = normalize_test_id(original)
        assert to_pytest_nodeid(stored, "toolz/tests/test_dicttoolz.py") == original


class TestNormalizeTestIdEdgeCases:
    def test_bare_module_id_with_no_test_name(self):
        from app.analysis.impact import normalize_test_id

        # a coverage context that's just a file path with no ::testname
        # (e.g. import-time execution outside any test) still normalizes cleanly
        assert normalize_test_id("toolz/tests/test_utils.py") == "toolz.tests.test_utils"


class TestBuildDependencyGraphCommitFilter:
    def test_commit_sha_isolates_coverage_by_commit(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.analysis.impact import build_dependency_graph
        from app.database import Base
        from app.models import Repo, RunSource
        from app.models import TestRun as TestRunModel

        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()

        repo = Repo(name="r", url=None)
        db.add(repo)
        db.commit()

        cov_a = {"files": {"a.py": {"contexts": {"1": ["a.py::test_x|run"]}}}}
        cov_b = {"files": {"b.py": {"contexts": {"1": ["b.py::test_y|run"]}}}}
        db.add(TestRunModel(repo_id=repo.id, commit_sha="commit_a", source=RunSource.COVERAGE, coverage_data=cov_a))
        db.add(TestRunModel(repo_id=repo.id, commit_sha="commit_b", source=RunSource.COVERAGE, coverage_data=cov_b))
        db.commit()

        graph_a = build_dependency_graph(db, repo.id, commit_sha="commit_a")
        assert set(graph_a.keys()) == {"a.py"}

        graph_all = build_dependency_graph(db, repo.id)
        assert set(graph_all.keys()) == {"a.py", "b.py"}

        db.close()
