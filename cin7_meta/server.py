"""FastMCP server setup and tool registration for mcp-cin7-meta."""

from fastmcp import FastMCP

from .resources import endpoints, invoke, issues
from .utils.logging import setup_logging

setup_logging()


def create_mcp_server(auth=None) -> FastMCP:
    """Create and configure the FastMCP server with the four generic tools.

    Args:
        auth: Optional auth provider (e.g., `ScalekitProvider`) for OAuth.
    """
    mcp = FastMCP(
        name="Cin7 Core Meta MCP Server",
        instructions=(
            "MCP server providing API-walking access to the Cin7 Core REST API. "
            "Use `list_api_endpoints` to find endpoints by keyword, "
            "`get_api_endpoint_schema` to inspect an endpoint's params and body schema, "
            "and `invoke_api_endpoint` to run a validated request. "
            "Use `report_issue` to file a structured bug report when a tool can't "
            "accomplish what you need."
        ),
        auth=auth,
    )

    mcp.tool()(endpoints.list_api_endpoints)
    mcp.tool()(endpoints.get_api_endpoint_schema)
    mcp.tool()(invoke.invoke_api_endpoint)
    mcp.tool()(issues.report_issue)

    return mcp
