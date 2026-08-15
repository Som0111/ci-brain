"""Parses `coverage json` output. Stored as-is for now; Phase 4 builds the
file-to-test dependency graph from data accumulated across runs."""

import json


class CoverageParseError(ValueError):
    pass


def parse_coverage_json(raw: bytes) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoverageParseError(f"not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise CoverageParseError("top-level coverage JSON must be an object")

    if "files" not in data:
        raise CoverageParseError("coverage JSON missing required 'files' key (expected `coverage json` output)")

    if not isinstance(data["files"], dict):
        raise CoverageParseError("'files' key must be an object mapping file path -> coverage data")

    return data
