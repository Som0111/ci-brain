import logging

import pytest

from app import logging_config
from app.config import settings

LEVELS = [("debug", logging.DEBUG), ("WARNING", logging.WARNING), ("nonsense", logging.INFO)]


@pytest.mark.parametrize("name,expected", LEVELS)
def test_log_level_from_settings(monkeypatch, name, expected):
    seen = {}
    monkeypatch.setattr(settings, "log_level", name)
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: seen.update(kw))
    logging_config.configure_logging()
    assert seen["level"] == expected


def test_no_print_calls_in_app_package():
    import pathlib

    offenders = [str(p) for p in pathlib.Path("app").rglob("*.py") if "print(" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_ingest_failure_log_has_no_traceback_or_payload_by_default(client, repo_id, monkeypatch, caplog):
    import app.api.runs as runs

    def boom(*a, **k):
        from sqlalchemy.exc import OperationalError

        raise OperationalError("SELECT secret", {}, Exception("password=hunter2"))

    monkeypatch.setattr(runs, "_get_or_create_test_case", boom)
    xml = b'<testsuite><testcase classname="a" name="UPLOADED-MARKER"/></testsuite>'
    with caplog.at_level(logging.WARNING):
        assert client.post(f"/repos/{repo_id}/runs", files={"junit_xml": ("j.xml", xml, "text/xml")}).status_code == 503
    rec = [r for r in caplog.records if "ingestion failed" in r.getMessage()][0]
    assert "OperationalError" in rec.getMessage()
    assert not rec.exc_info  # traceback (internal paths) only at LOG_LEVEL=DEBUG
    assert "hunter2" not in caplog.text and "UPLOADED-MARKER" not in caplog.text


def test_successful_ingest_logs_counts_only(client, repo_id, caplog):
    xml = b'<testsuite><testcase classname="a" name="UPLOADED-MARKER"/></testsuite>'
    with caplog.at_level(logging.INFO):
        client.post(f"/repos/{repo_id}/runs", files={"junit_xml": ("j.xml", xml, "text/xml")})
    assert "1 results" in caplog.text and "UPLOADED-MARKER" not in caplog.text
