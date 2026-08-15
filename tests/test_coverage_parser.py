import pytest

from app.parsers.coverage_json import CoverageParseError, parse_coverage_json


def test_parses_valid_coverage_json():
    raw = b'{"meta": {}, "files": {"app/foo.py": {"summary": {"percent_covered": 90.0}}}}'
    data = parse_coverage_json(raw)
    assert "app/foo.py" in data["files"]


@pytest.mark.parametrize(
    "raw",
    [
        b"not json {{{",
        b"[1, 2, 3]",
        b'{"meta": {}}',
        b'{"files": "not-an-object"}',
    ],
)
def test_malformed_input_raises(raw):
    with pytest.raises(CoverageParseError):
        parse_coverage_json(raw)
