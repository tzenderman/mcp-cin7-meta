"""Tests for the report_issue MCP tool."""

import json
import re

import pytest

from cin7_meta.resources.issues import report_issue


def _parse_line(text: str) -> dict:
    """Strip the `ISSUE_REPORT ` prefix and parse the JSON payload."""
    return json.loads(text.strip().split("ISSUE_REPORT ", 1)[1])


@pytest.mark.asyncio
class TestReportIssue:
    async def test_successful_report_returns_id_and_friendly_message(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.log"))
        result = await report_issue(
            summary="thing broke",
            tool_name="invoke_api_endpoint",
            tool_arguments={"method": "GET", "path": "Product"},
            observed_behavior="got 200 but no products",
            expected_behavior="should have products",
        )
        assert re.fullmatch(r"rpt_[0-9a-f]{8}", result["report_id"])
        assert result["stored_in_file"] is True
        assert result["stored_in_log"] is True
        assert "thanks" in result and isinstance(result["thanks"], str)

    async def test_jsonl_contains_all_required_fields(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        await report_issue(
            summary="thing broke",
            tool_name="invoke_api_endpoint",
            tool_arguments={"method": "POST", "path": "Sale"},
            observed_behavior="x",
            expected_behavior="y",
        )
        payload = _parse_line(path.read_text())
        assert payload["summary"] == "thing broke"
        assert payload["tool_name"] == "invoke_api_endpoint"
        assert payload["tool_arguments"]["method"] == "POST"
        assert payload["observed_behavior"] == "x"
        assert payload["expected_behavior"] == "y"

    async def test_optional_fields_passthrough(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        await report_issue(
            summary="x",
            tool_name="invoke_api_endpoint",
            tool_arguments={"a": 1},
            observed_behavior="o",
            expected_behavior="e",
            severity="high",
            error_message="Cin7APIError: boom",
            response_excerpt="some body",
            client_context="claude opus 4.7",
        )
        payload = _parse_line(path.read_text())
        assert payload["severity"] == "high"
        assert payload["error_message"] == "Cin7APIError: boom"
        assert payload["response_excerpt"] == "some body"
        assert payload["client_context"] == "claude opus 4.7"

    async def test_response_excerpt_truncated_at_2000(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.log"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        huge = "X" * 5000
        await report_issue(
            summary="x",
            tool_name="invoke_api_endpoint",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
            response_excerpt=huge,
        )
        payload = _parse_line(path.read_text())
        assert payload["response_excerpt"].endswith("... [truncated]")
        assert len(payload["response_excerpt"]) <= 2050

    async def test_invalid_severity_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.log"))
        result = await report_issue(
            summary="x",
            tool_name="invoke_api_endpoint",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
            severity="critical",
        )
        assert "error" in result
        assert "severity" in result["error"].lower()

    async def test_invalid_tool_name_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.log"))
        result = await report_issue(
            summary="x",
            tool_name="not_a_real_tool",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
        )
        assert "error" in result
        assert "tool_name" in result["error"].lower()

    async def test_required_fields_validated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.log"))
        result = await report_issue(
            summary="",
            tool_name="invoke_api_endpoint",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
        )
        assert "error" in result

    async def test_file_failure_still_returns_success(self, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", "/dev/null/cannot/issues.log")
        result = await report_issue(
            summary="x",
            tool_name="invoke_api_endpoint",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
        )
        assert result["report_id"].startswith("rpt_")
        assert result["stored_in_file"] is False
        assert result["stored_in_log"] is True
