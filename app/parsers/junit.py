"""Parses pytest JUnit XML into plain records the ingestion endpoint can store."""

from dataclasses import dataclass

from lxml import etree


class JUnitParseError(ValueError):
    pass


def file_path_from_classname(classname: str) -> str:
    """Derive the test's source file from a JUnit ``classname``.

    pytest does not always emit a ``file`` attribute, and its ``classname``
    folds the class into the dotted module path
    (``toolz.tests.test_dicttoolz.TestDict``). Naively replacing dots with
    slashes turns the class into a directory
    (``toolz/tests/test_dicttoolz/TestDict.py``) - a path that doesn't exist,
    which breaks anything that joins test results back to real files.

    Class components are stripped using the PEP 8 convention that classes are
    CapWords and modules/packages are lowercase. A module named ``Foo.py``
    would defeat this, which is unconventional enough to accept.
    """
    parts = classname.split(".")
    while len(parts) > 1 and parts[-1][:1].isupper():
        parts.pop()
    return "/".join(parts) + ".py"


@dataclass
class ParsedTestResult:
    node_id: str
    file_path: str
    status: str  # "passed" | "failed" | "skipped" | "error"
    duration_seconds: float | None
    message: str | None


def parse_junit_xml(raw: bytes) -> list[ParsedTestResult]:
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError as exc:
        raise JUnitParseError(f"not valid XML: {exc}") from exc

    if root.tag == "testsuites":
        testcases = root.findall(".//testcase")
    elif root.tag == "testsuite":
        testcases = root.findall("./testcase")
    else:
        raise JUnitParseError(f"expected <testsuites> or <testsuite> root, got <{root.tag}>")

    if not testcases and root.tag == "testsuites" and len(root) == 0:
        raise JUnitParseError("no <testsuite> elements found under <testsuites>")

    results: list[ParsedTestResult] = []
    for tc in testcases:
        name = tc.get("name")
        classname = tc.get("classname")
        if not name or not classname:
            raise JUnitParseError(f"<testcase> missing required name/classname attribute: {etree.tostring(tc)!r}")

        node_id = f"{classname}::{name}"
        file_path = tc.get("file") or file_path_from_classname(classname)

        duration_raw = tc.get("time")
        try:
            duration = float(duration_raw) if duration_raw is not None else None
        except ValueError as exc:
            raise JUnitParseError(f"non-numeric time={duration_raw!r} on testcase {node_id}") from exc

        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")

        if error is not None:
            status = "error"
            message = error.get("message") or (error.text or "").strip() or None
        elif failure is not None:
            status = "failed"
            message = failure.get("message") or (failure.text or "").strip() or None
        elif skipped is not None:
            status = "skipped"
            message = skipped.get("message") or (skipped.text or "").strip() or None
        else:
            status = "passed"
            message = None

        results.append(
            ParsedTestResult(
                node_id=node_id,
                file_path=file_path,
                status=status,
                duration_seconds=duration,
                message=message,
            )
        )

    return results
