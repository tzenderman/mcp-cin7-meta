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


class TestRedaction:
    """Reports carry model-supplied arguments and response excerpts, which can
    contain credentials or customer PII. Both sinks (log line + file) must
    receive the redacted payload."""

    def _record(self, tmp_path, monkeypatch, caplog, payload):
        path = tmp_path / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        with caplog.at_level(logging.INFO):
            record_issue(payload)
        log_line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("ISSUE_REPORT "))
        return path.read_text(), log_line

    def test_redacts_values_under_secret_keys_at_any_depth(self, tmp_path, monkeypatch, caplog):
        stored, logged = self._record(tmp_path, monkeypatch, caplog, {
            "tool_arguments": {
                "headers": {"Authorization": "Bearer abc123", "X-Access-Token": "tok_live"},
                "config": [{"client_secret": "s3cr3t", "password": "hunter2", "api_key": "k"}],
            },
        })
        for sink in (stored, logged):
            for leaked in ("abc123", "tok_live", "s3cr3t", "hunter2"):
                assert leaked not in sink
            assert "[REDACTED]" in sink

    def test_redacts_cin7_auth_headers_and_env_names(self, tmp_path, monkeypatch, caplog):
        # "applicationkey" does not match api[_-]?key, so Cin7's own credential
        # names need explicit coverage.
        account_id = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
        app_key = "9a8b7c6d-5e4f-3a2b-1c0d-ef0123456789"
        stored, logged = self._record(tmp_path, monkeypatch, caplog, {
            "tool_arguments": {
                "headers": {"api-auth-accountid": account_id, "api-auth-applicationkey": app_key},
                "env": {"CIN7_ACCOUNT_ID": account_id, "CIN7_API_KEY": app_key},
            },
        })
        for sink in (stored, logged):
            assert account_id not in sink
            assert app_key not in sink

    def test_masks_email_addresses(self, tmp_path, monkeypatch, caplog):
        stored, logged = self._record(tmp_path, monkeypatch, caplog, {
            "response_excerpt": '{"Customer": "Jane", "Email": "jane.doe@example.com"}',
        })
        for sink in (stored, logged):
            assert "jane.doe@example.com" not in sink

    def test_keeps_debugging_data_intact(self, tmp_path, monkeypatch, caplog):
        args = {
            "method": "GET",
            "path": "Product",
            "query_params": {"ID": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "Sku": "WIDGET-001"},
            # Real Cin7 fields that merely contain "AccountId" are not credentials.
            "body": {"BankAccountId": "b1c2d3e4-0000-1111-2222-333344445555", "AccountID": "200"},
        }
        stored, _ = self._record(tmp_path, monkeypatch, caplog, {
            "summary": "product lookup failed",
            "tool_arguments": args,
        })
        payload = _parse_line(stored.strip())
        assert payload["tool_arguments"] == args
        assert payload["summary"] == "product lookup failed"
