"""MCP tool: report_issue.

Lets the model file a structured bug report when it can't accomplish a task.
The payload is written through `utils.issue_reporter.record_issue` which
appends a single `ISSUE_REPORT <json>` line to both the module logger
(stderr / Render log stream) and `data/issue_reports.log`. Developers can
review captured reports with `grep ISSUE_REPORT` against either source.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from cin7_meta.utils.issue_reporter import record_issue
from cin7_meta.utils.logging import truncate

logger = logging.getLogger(__name__)

ALLOWED_TOOL_NAMES = {"list_api_endpoints", "get_api_endpoint_schema", "invoke_api_endpoint"}
ALLOWED_SEVERITIES = {"low", "medium", "high"}


def _err(msg: str) -> dict[str, Any]:
    return {"error": msg}


async def report_issue(
    summary: str,
    tool_name: Literal["list_api_endpoints", "get_api_endpoint_schema", "invoke_api_endpoint"],
    tool_arguments: dict[str, Any],
    observed_behavior: str,
    expected_behavior: str,
    severity: Literal["low", "medium", "high"] = "medium",
    error_message: str | None = None,
    response_excerpt: str | None = None,
    client_context: str | None = None,
) -> dict[str, Any]:
    """File a structured bug report for later developer review.

    Args:
        summary: One-line headline of what went wrong.
        tool_name: Which MCP tool was being used when the issue occurred.
            One of `list_api_endpoints`, `get_api_endpoint_schema`,
            `invoke_api_endpoint`.
        tool_arguments: The exact kwargs you passed to the tool. Include
            enough information for someone else to reproduce the call.
        observed_behavior: What actually happened. Be specific.
        expected_behavior: What you expected to happen instead.
        severity: `low`, `medium`, or `high`. Default `medium`.
        error_message: Exception class + message, if one was raised.
        response_excerpt: Truncated snippet of the response body.
            Capped at 2000 chars.
        client_context: Optional notes — model name, conversation topic,
            any context that would help the developer reproduce.

    Returns:
        `{"report_id", "stored_in_file", "stored_in_log", "thanks"}` on success,
        or `{"error": "..."}` if a required field is invalid.
    """
    if not summary or not summary.strip():
        return _err("summary is required.")
    if tool_name not in ALLOWED_TOOL_NAMES:
        return _err(
            f"tool_name must be one of {sorted(ALLOWED_TOOL_NAMES)}; got {tool_name!r}."
        )
    if not isinstance(tool_arguments, dict):
        return _err("tool_arguments must be a JSON object describing the call.")
    if not observed_behavior or not observed_behavior.strip():
        return _err("observed_behavior is required.")
    if not expected_behavior or not expected_behavior.strip():
        return _err("expected_behavior is required.")
    if severity not in ALLOWED_SEVERITIES:
        return _err(
            f"severity must be one of {sorted(ALLOWED_SEVERITIES)}; got {severity!r}."
        )

    payload: dict[str, Any] = {
        "summary": summary,
        "tool_name": tool_name,
        "tool_arguments": tool_arguments,
        "observed_behavior": observed_behavior,
        "expected_behavior": expected_behavior,
        "severity": severity,
    }
    if error_message is not None:
        payload["error_message"] = error_message
    if response_excerpt is not None:
        payload["response_excerpt"] = truncate(response_excerpt, max_len=2000)
    if client_context is not None:
        payload["client_context"] = client_context

    report_id, wrote_to_file = record_issue(payload)

    return {
        "report_id": report_id,
        "stored_in_file": wrote_to_file,
        "stored_in_log": True,
        "thanks": (
            f"Issue {report_id} logged. The developer will review and follow up. "
            "Quote this report_id if you mention the issue later."
        ),
    }
