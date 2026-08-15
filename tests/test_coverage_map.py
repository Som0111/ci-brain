from scripts.coverage_map import build_file_test_map


def test_maps_file_to_tests_that_executed_it():
    coverage_data = {
        "files": {
            "toolz/dicttoolz.py": {
                "contexts": {
                    "12": ["", "toolz/tests/test_dicttoolz.py::test_merge|setup",
                           "toolz/tests/test_dicttoolz.py::test_merge|run"],
                    "13": ["toolz/tests/test_dicttoolz.py::test_merge|run",
                           "toolz/tests/test_curried.py::test_merge|run"],
                }
            },
            "toolz/utils.py": {
                "contexts": {
                    "1": [""],  # only hit at collection time, never by a real test
                }
            },
        }
    }

    result = build_file_test_map(coverage_data)

    assert result["toolz/dicttoolz.py"] == {
        "toolz/tests/test_dicttoolz.py::test_merge",
        "toolz/tests/test_curried.py::test_merge",
    }
    assert "toolz/utils.py" not in result  # no real test executed any of its lines


def test_handles_windows_backslash_paths():
    coverage_data = {
        "files": {
            "toolz\\dicttoolz.py": {
                "contexts": {"1": ["toolz/tests/test_dicttoolz.py::test_merge|run"]}
            }
        }
    }

    result = build_file_test_map(coverage_data)

    assert "toolz/dicttoolz.py" in result
    assert "toolz\\dicttoolz.py" not in result
