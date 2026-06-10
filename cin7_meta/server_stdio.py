"""Stdio transport entry point for local usage (Claude Desktop, etc.)."""

import os
from pathlib import Path

from dotenv import load_dotenv

from .server import create_mcp_server
from .utils.spec_loader import get_spec


def main():
    """Run MCP server with stdio transport."""
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    load_dotenv(env_file)

    missing = [v for v in ("CIN7_ACCOUNT_ID", "CIN7_API_KEY") if not os.getenv(v)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and configure your Cin7 credentials."
        )

    # Fail loud at startup if the vendored spec is missing or malformed,
    # rather than silently failing every tool call.
    get_spec()

    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
