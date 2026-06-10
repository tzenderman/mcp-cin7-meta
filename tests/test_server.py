"""Tests for FastMCP server registration."""

import json

import pytest

from cin7_meta.server import create_mcp_server

EXPECTED_TOOLS = {
    "list_api_endpoints",
    "get_api_endpoint_schema",
    "invoke_api_endpoint",
    "report_issue",
}


@pytest.mark.asyncio
async def test_all_tools_registered(monkeypatch, tmp_path):
    """Server should register exactly the 4 generic tools — no more, no less."""
    spec_path = tmp_path / "spec.json"
    from tests.fixtures.mini_spec import MINI_CATALOG
    spec_path.write_text(json.dumps(MINI_CATALOG))
    monkeypatch.setenv("CIN7_SPEC_PATH", str(spec_path))

    mcp = create_mcp_server()
    tools = await mcp.get_tools()
    assert set(tools.keys()) == EXPECTED_TOOLS, (
        f"unexpected tools registered: extra={set(tools.keys()) - EXPECTED_TOOLS}, "
        f"missing={EXPECTED_TOOLS - set(tools.keys())}"
    )


def test_server_name_and_instructions(monkeypatch, tmp_path):
    spec_path = tmp_path / "spec.json"
    from tests.fixtures.mini_spec import MINI_CATALOG
    spec_path.write_text(json.dumps(MINI_CATALOG))
    monkeypatch.setenv("CIN7_SPEC_PATH", str(spec_path))

    mcp = create_mcp_server()
    assert "Cin7 Core Meta" in mcp.name
    # instructions should mention the api-walking pattern
    assert "api" in (mcp.instructions or "").lower()
