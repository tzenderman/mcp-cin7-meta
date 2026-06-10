"""Tests for record_issue: the structured log-line writer behind report_issue."""

import json
import logging
import re
import sys

from cin7_meta.utils.issue_reporter import record_issue


def _parse_line(line: str) -> dict:
    """Strip the `ISSUE_REPORT ` prefix and parse the JSON payload."""
    return json.loads(line.split("ISSUE_REPORT ", 1)[1])


class TestRecordIssue:
    def test_returns_report_id_and_file_flag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.log"))
        report_id, wrote_to_file = record_issue({"summary": "x"})
        assert report_id.startswith("rpt_")
        assert wrote_to_file is True

    def test_report_id_format(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.log"))
        report_id, _ = record_issue({"summary": "x"})
        assert re.fullmatch(r"rpt_[0-9a-f]{8}", report_id), report_id

    def test_appends_one_line_per_call(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        record_issue({"summary": "first"})
        record_issue({"summary": "second"})
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert _parse_line(lines[0])["summary"] == "first"
        assert _parse_line(lines[1])["summary"] == "second"

    def test_stamps_required_metadata(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        record_issue({"summary": "x"})
        payload = _parse_line(path.read_text().strip())
        assert payload["report_id"].startswith("rpt_")
        assert payload["timestamp"]
        assert payload["server"] == "mcp-cin7-meta"
        assert payload["server_version"]
        assert payload["python_version"] == sys.version.split()[0]

    def test_caller_payload_overrides_unprotected_keys(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        record_issue({"summary": "caller", "report_id": "rpt_evil!"})
        payload = _parse_line(path.read_text().strip())
        assert payload["summary"] == "caller"
        assert re.fullmatch(r"rpt_[0-9a-f]{8}", payload["report_id"])

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        path = tmp_path / "nested" / "deeper" / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        record_issue({"summary": "x"})
        assert path.exists()

    def test_unwritable_path_falls_back_to_log_only(self, monkeypatch, caplog):
        monkeypatch.setenv("ISSUE_REPORT_PATH", "/dev/null/cannot-create/issues.log")
        with caplog.at_level(logging.INFO):
            report_id, wrote_to_file = record_issue({"summary": "boom"})
        assert wrote_to_file is False
        assert report_id.startswith("rpt_")
        assert any("ISSUE_REPORT" in rec.message for rec in caplog.records)

    def test_always_logs_structured_line(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.log"))
        with caplog.at_level(logging.INFO, logger="cin7_meta.utils.issue_reporter"):
            record_issue({"summary": "logme"})
        log_messages = [r.message for r in caplog.records if "ISSUE_REPORT" in r.message]
        assert log_messages
        json_portion = log_messages[0].split("ISSUE_REPORT ", 1)[1]
        parsed = json.loads(json_portion)
        assert parsed["summary"] == "logme"

    def test_file_lines_use_issue_report_prefix(self, tmp_path, monkeypatch):
        """File format mirrors the stderr/Render log format: `ISSUE_REPORT <json>`."""
        path = tmp_path / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        record_issue({"summary": "prefixed"})
        line = path.read_text().strip()
        assert line.startswith("ISSUE_REPORT "), f"got: {line[:80]!r}"
        json_portion = line.split("ISSUE_REPORT ", 1)[1]
        parsed = json.loads(json_portion)
        assert parsed["summary"] == "prefixed"
