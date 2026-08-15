from app.analysis.clustering import FailureRecord, cluster_failures, extract_call_hint


class TestExtractCallHint:
    def test_no_hint_when_no_where_clause(self):
        assert extract_call_hint("assert 1 == 2") is None

    def test_extracts_plain_function_call(self):
        msg = "assert 'a' == 1\n +  where 1 = first(<islice object at 0x1>)"
        assert extract_call_hint(msg) == "first"

    def test_extracts_function_repr_form(self):
        msg = "assert None == 0  +  where None = <function identity at 0x1>(*(0,), **{})"
        assert extract_call_hint(msg) == "identity"

    def test_uses_innermost_when_multiple_where_clauses(self):
        msg = (
            "assert 'a' == 1\n"
            " +  where 1 = first(<islice object at 0x1>)\n"
            " +    where <islice object at 0x1> = rest(<chain object at 0x2>)\n"
            " +      where <chain object at 0x2> = interpose('a', range(0, 10))"
        )
        # pytest lists innermost (most specific) first: `first()` produced the
        # directly-compared value, `interpose()` is further up the call chain.
        assert extract_call_hint(msg) == "first"


class TestClusterFailures:
    def test_same_file_no_hint_groups_together(self):
        files = frozenset({"toolz/dicttoolz.py"})
        records = [
            FailureRecord("t1::test_merge", "t1.py", "assert {1: 1} == {1: 1, 2: 2}"),
            FailureRecord("t1::test_merge_iterable_arg", "t1.py", "assert {1: 1} == {1: 1, 3: 4}"),
        ]
        clusters = cluster_failures(records, {r.node_id: files for r in records})
        assert len(clusters) == 1
        assert clusters[0].size == 2
        assert clusters[0].covered_files == files

    def test_different_files_split_into_different_clusters(self):
        records = [
            FailureRecord("t1::test_merge", "t1.py", "assert 1 == 2"),
            FailureRecord("t1::test_compose", "t1.py", "assert None == 0"),
        ]
        covered = {
            "t1::test_merge": frozenset({"toolz/dicttoolz.py"}),
            "t1::test_compose": frozenset({"toolz/functoolz.py"}),
        }
        clusters = cluster_failures(records, covered)
        assert len(clusters) == 2

    def test_call_hint_splits_same_file_when_bugs_differ(self):
        # both tests only cover itertoolz.py, but one message names the culprit
        files = frozenset({"toolz/itertoolz.py"})
        records = [
            FailureRecord("t1::test_unique", "t1.py", "assert (1, 2, 1) == (1, 2)"),
            FailureRecord(
                "t1::test_interpose", "t1.py",
                "assert 'a' == 1\n +  where 1 = first(<islice object at 0x1>)",
            ),
        ]
        clusters = cluster_failures(records, {r.node_id: files for r in records})
        assert len(clusters) == 2
        hints = {c.call_hint for c in clusters}
        assert hints == {None, "first"}

    def test_no_coverage_data_falls_back_to_empty_key_not_crash(self):
        records = [FailureRecord("t1::test_new", "t1.py", "assert False")]
        clusters = cluster_failures(records, {})
        assert len(clusters) == 1
        assert clusters[0].covered_files == frozenset()

    def test_largest_cluster_first(self):
        files_a = frozenset({"a.py"})
        files_b = frozenset({"b.py"})
        records = [
            FailureRecord("t1::x", "t1.py", "m"),
            FailureRecord("t1::y", "t1.py", "m"),
            FailureRecord("t1::z", "t1.py", "m"),
            FailureRecord("t1::w", "t1.py", "m"),
        ]
        covered = {"t1::x": files_a, "t1::y": files_a, "t1::z": files_a, "t1::w": files_b}
        clusters = cluster_failures(records, covered)
        assert clusters[0].size == 3
        assert clusters[1].size == 1

    def test_representative_is_shortest_message(self):
        files = frozenset({"a.py"})
        records = [
            FailureRecord("t1::x", "t1.py", "short"),
            FailureRecord("t1::y", "t1.py", "a much longer failure message with detail"),
        ]
        clusters = cluster_failures(records, {r.node_id: files for r in records})
        assert clusters[0].representative.node_id == "t1::x"
