"""
Turn one run's raw `coverage json --show-contexts` output into a
file -> {test node ids that executed a line in that file} map.

This is a single-run view for the replay harness's own spot-checking.
Phase 4 aggregates this same shape of data across many stored runs into
the full dependency graph.
"""


def build_file_test_map(coverage_data: dict) -> dict[str, set[str]]:
    file_test_map: dict[str, set[str]] = {}

    for file_path, file_data in coverage_data["files"].items():
        tests: set[str] = set()
        for contexts in file_data.get("contexts", {}).values():
            for ctx in contexts:
                if not ctx:
                    continue  # empty context = collection-time execution, not a real test
                node_id = ctx.split("|", 1)[0]  # strip pytest-cov's "|setup"/"|run"/"|teardown" suffix
                tests.add(node_id)
        if tests:
            file_test_map[file_path.replace("\\", "/")] = tests

    return file_test_map
