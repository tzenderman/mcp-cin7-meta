"""FastMCP server setup and tool registration for mcp-cin7-meta."""

from fastmcp import FastMCP

from .resources import endpoints, invoke, issues
from .utils.logging import setup_logging
from .utils.read_only import is_read_only

setup_logging()

_BASE_INSTRUCTIONS = (
    "MCP server providing API-walking access to the Cin7 Core REST API. "
    "Use `list_api_endpoints` to find endpoints by keyword, "
    "`get_api_endpoint_schema` to inspect an endpoint's params and body schema, "
    "and `invoke_api_endpoint` to run a validated request. "
    "Use `report_issue` to file a structured bug report when a tool can't "
    "accomplish what you need."
)

_READ_ONLY_INSTRUCTIONS = (
    " THIS SERVER IS IN READ-ONLY MODE: only GET requests are executed. "
    "`list_api_endpoints` still returns write endpoints because it describes the "
    "Cin7 API, not your permissions — but invoking any of them is refused before "
    "the request leaves this process. Do not attempt writes and do not hunt for a "
    "workaround; state what would need to change and hand it to a human or to an "
    "agent that owns Cin7 writes."
)


def create_mcp_server(auth=None) -> FastMCP:
    """Create and configure the FastMCP server with the four generic tools.

    Args:
        auth: Optional auth provider (e.g., `ScalekitProvider`) for OAuth.
    """
    instructions = _BASE_INSTRUCTIONS
    if is_read_only():
        instructions += _READ_ONLY_INSTRUCTIONS

    mcp = FastMCP(
        name="Cin7 Core Meta MCP Server",
        instructions=instructions,
        auth=auth,
    )

    mcp.tool()(endpoints.list_api_endpoints)
    mcp.tool()(endpoints.get_api_endpoint_schema)
    mcp.tool()(invoke.invoke_api_endpoint)
    mcp.tool()(issues.report_issue)

    return mcp
