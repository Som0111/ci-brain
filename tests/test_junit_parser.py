import pytest

from app.parsers.junit import JUnitParseError, parse_junit_xml

SAMPLE = (
    b'<testsuites><testsuite name="pytest" tests="1">'
    b'<testcase classname="tests.test_math" name="test_add" file="tests/test_math.py" time="0.001" />'
    b"</testsuite></testsuites>"
)


def test_parses_passed_test():
    results = parse_junit_xml(SAMPLE)
    assert len(results) == 1
    r = results[0]
    assert r.node_id == "tests.test_math::test_add"
    assert r.file_path == "tests/test_math.py"
    assert r.status == "passed"
    assert r.duration_seconds == 0.001
    assert r.message is None


def test_parses_failure_error_skipped():
    xml = (
        b"<testsuite>"
        b'<testcase classname="t" name="fail" time="0.1"><failure message="boom">trace</failure></testcase>'
        b'<testcase classname="t" name="err" time="0.1"><error message="oops">trace</error></testcase>'
        b'<testcase classname="t" name="skip" time="0.0"><skipped message="nope" /></testcase>'
        b"</testsuite>"
    )
    results = {r.node_id.split("::")[1]: r for r in parse_junit_xml(xml)}
    assert results["fail"].status == "failed"
    assert results["fail"].message == "boom"
    assert results["err"].status == "error"
    assert results["skip"].status == "skipped"


def test_bare_testsuite_root_is_accepted():
    xml = b'<testsuite><testcase classname="t" name="ok" time="0.0" /></testsuite>'
    results = parse_junit_xml(xml)
    assert results[0].status == "passed"


def test_missing_file_attribute_falls_back_to_classname():
    xml = b'<testsuite><testcase classname="pkg.mod" name="ok" time="0.0" /></testsuite>'
    results = parse_junit_xml(xml)
    assert results[0].file_path == "pkg/mod.py"


@pytest.mark.parametrize(
    "raw",
    [
        b"not xml at all <<<",
        b"<unexpected_root></unexpected_root>",
        b'<testsuite><testcase name="missing_classname" time="0.0" /></testsuite>',
        b'<testsuite><testcase classname="t" name="bad_time" time="not-a-number" /></testsuite>',
    ],
)
def test_malformed_input_raises(raw):
    with pytest.raises(JUnitParseError):
        parse_junit_xml(raw)


def test_file_path_strips_class_component():
    from app.parsers.junit import file_path_from_classname

    # module-level test function: classname is purely the module path
    assert file_path_from_classname("toolz.sandbox.tests.test_core") == "toolz/sandbox/tests/test_core.py"
    # class-based test: the CapWords class must not become a directory
    assert file_path_from_classname("toolz.tests.test_dicttoolz.TestDict") == "toolz/tests/test_dicttoolz.py"
    # nested classes
    assert file_path_from_classname("pkg.mod.Outer.Inner") == "pkg/mod.py"
    # single bare module
    assert file_path_from_classname("test_thing") == "test_thing.py"
