# Cin7 Core Meta MCP Server

This is a Model Context Protocol (MCP) server for the [Cin7 Core (DEAR) API](https://dearinventory.docs.apiary.io/). Instead of exposing one tool per Cin7 endpoint, this server exposes **three generic API-walking tools** plus a structured bug-report tool. The model finds what it needs at runtime: list endpoints → read an endpoint's schema → invoke it.

It's a sibling to [`mcp-cin7-core`](../mcp-cin7-core) — that server ships hand-curated tools (`cin7_products`, `cin7_create_purchase_order`, …) for common operations. This one covers the **full** Cin7 Core API surface (Brands, Categories, Carriers, Chart of Accounts, Disassembly, Finished Goods, anything Cin7 ships) with a tiny tool list that doesn't grow as the API grows. Both servers can be installed in the same client; they're complementary.

## Features

- Four MCP tools that cover the full Cin7 Core REST API surface
- API-walking pattern (`list → describe → invoke`) keeps the tool list tiny
- Request validation against a vendored API Blueprint spec — unknown endpoints, wrong methods, missing required params, and type mismatches are caught **before** any network call
- Rate-limit passthrough — Cin7's `X-RateLimit-Remaining` header is surfaced so the model can self-throttle
- Structured bug-report tool — appends `ISSUE_REPORT <json>` to both a controlled file and stderr
- ScaleKit OAuth 2.0 / Streamable HTTP transport for remote deployments
- Stdio transport for local Claude Desktop integration
- MCP protocol compliance

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- A Cin7 Core (DEAR) account with API access — get your `AccountID` and `Application Key` from **Integrations → API**

## Docs and Links

- [Cin7 Core API Reference (Apiary)](https://dearinventory.docs.apiary.io/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [`docs/tools.md`](docs/tools.md) — full reference for the four MCP tools
- [`docs/spec_refresh.md`](docs/spec_refresh.md) — how/when to refresh the vendored API Blueprint spec

## Setup

### Get Cin7 Core API credentials

1. Log in to Cin7 Core (DEAR)
2. Navigate to **Integrations → API**
3. Copy the **AccountID** and create/copy the **Application Key**

### Authentication

There are 2 modes of running the Cin7 Core Meta MCP server:

#### 1. Streamable HTTP with OAuth (Recommended for production)

This mode runs the server as a web service with OAuth 2.0 authentication via [ScaleKit](https://scalekit.com/). This is the recommended approach for shared or remote deployments, including connecting via Claude Desktop's remote MCP connector.

**Required environment variables:**
- `CIN7_ACCOUNT_ID` - Your Cin7 AccountID
- `CIN7_API_KEY` - Your Cin7 Application Key
- `SCALEKIT_ENVIRONMENT_URL` - ScaleKit environment URL (e.g., `https://yourapp.scalekit.com`)
- `SCALEKIT_CLIENT_ID` - ScaleKit application client ID
- `SCALEKIT_CLIENT_SECRET` - ScaleKit application client secret
- `SCALEKIT_RESOURCE_ID` - ScaleKit resource identifier (e.g., `res_xxx`)
- `SCALEKIT_INTERCEPTOR_SECRET` - Secret for verifying interceptor payloads
- `SERVER_URL` - Your MCP server's public URL (e.g., `https://your-server.example.com`)

**Optional:**
- `ALLOWED_EMAILS` - Comma-separated list of allowed email addresses (leave empty to allow all authenticated users)
- `CIN7_BASE_URL` - Override the Cin7 base URL (default `https://inventory.dearsystems.com/ExternalApi/v2/`)
- `ISSUE_REPORT_PATH` - Where `report_issue` appends its `ISSUE_REPORT <json>` lines (default `./data/issue_reports.log`)
- `MCP_LOG_LEVEL` - Logging level (default `INFO`)
- `MCP_LOG_FILE` - Enable file logging with rotation

**Running the server:**
```bash
uv run python -m cin7_meta.server_http
```

**Endpoints:**
- `GET /health` - Health check (no auth required)
- `GET /.well-known/oauth-protected-resource` - OAuth discovery (no auth required)
- `POST /mcp` - MCP endpoint (requires OAuth 2.0 Bearer token)

**Connecting from Claude Desktop (remote):**
1. Deploy your server (e.g., to Render — see [`render.yaml`](render.yaml))
2. Open **Claude Desktop** > **Settings** > **Connectors**
3. Click **"Add Connector"** and enter your server URL: `https://your-server.com/mcp`
4. Claude will auto-discover OAuth configuration
5. Click **"Authorize"** and log in

See [CLAUDE.md](CLAUDE.md) for detailed ScaleKit setup and interceptor configuration.

#### 2. Stdio Transport (Local development)

This mode runs the server locally using stdio transport for direct integration with Claude Desktop. No OAuth configuration needed — Cin7 credentials are used directly.

**Required environment variables:**
- `CIN7_ACCOUNT_ID`
- `CIN7_API_KEY`

**Optional:** `CIN7_BASE_URL`, `ISSUE_REPORT_PATH`, `MCP_LOG_LEVEL`, `MCP_LOG_FILE`.

**Claude Desktop configuration:**

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cin7-meta": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-cin7-meta",
        "run",
        "python",
        "-m",
        "cin7_meta.server_stdio"
      ],
      "env": {
        "CIN7_ACCOUNT_ID": "your-account-id",
        "CIN7_API_KEY": "your-application-key"
      }
    }
  }
}
```

Replace `/absolute/path/to/mcp-cin7-meta` with the actual path to your clone of this repository.

If you're running both servers together, give them distinct names (e.g. `cin7-core` for the curated server and `cin7-meta` for this one) so Claude lists their tools separately.

### Installation

```bash
# Create virtual environment and install dependencies
uv venv
uv pip install -e .

# Quick import check
uv run python -c "import cin7_meta.server; print('OK')"
```

### Vendor the API Blueprint spec (one-time)

This server validates requests against a vendored API Blueprint that ships at `cin7_meta/spec/cin7_v2.apib`, plus a derived normalized JSON catalog at `cin7_meta/spec/cin7_v2.json`. A fresh clone won't have these — generate them:

```bash
uv run python scripts/refresh_spec.py
```

Re-run any time the Cin7 API changes or you want to pick up new endpoints. See [`docs/spec_refresh.md`](docs/spec_refresh.md) for the full workflow.

### Testing with MCP Inspector

```bash
# Start the HTTP server
uv run python -m cin7_meta.server_http

# In another terminal, open MCP Inspector
npx @modelcontextprotocol/inspector http://localhost:3000/mcp
```

## Available MCP Tools

**API walking:**
- `list_api_endpoints(keyword, methods, limit)` — Ranked keyword search across endpoint paths, summaries, groups, and parameter names. Returns `{"results": [...], "total": int, "truncated": bool}`.
- `get_api_endpoint_schema(method, path)` — Return the full schema for one endpoint: query params (with types and defaults), request body schema, response schema, and JSON examples.

**Execution:**
- `invoke_api_endpoint(method, path, query_params, body)` — Validate, then execute, an arbitrary Cin7 Core API call. Validation errors (unknown endpoint, wrong method, missing required param, type mismatch) are returned **without** a network call. Returns `{"status", "data", "rate_limit_remaining"}` — use `rate_limit_remaining` for self-throttling.

**Issue reporting:**
- `report_issue(summary, tool_name, tool_arguments, observed_behavior, expected_behavior, ...)` — File a structured bug report when a tool doesn't behave as expected. Each report is appended as one `ISSUE_REPORT <json>` line to `data/issue_reports.log` *and* emitted on stderr in the same format, so reports survive even on hosts with ephemeral filesystems (Render's log stream captures the stderr line). Returns a `report_id` the model can quote in follow-ups.

For detailed signatures, examples, and return shapes, see [`docs/tools.md`](docs/tools.md).

For the underlying Cin7 Core API documentation, refer to the [Cin7 Core API Reference](https://dearinventory.docs.apiary.io/).

## For Developers

### Running Tests

```bash
# Full test suite
uv run pytest -v

# Quick pass/fail check
uv run pytest --tb=short

# Specific test file
uv run pytest tests/test_invoke_api_endpoint.py -v
```

### Contributing — Test-Driven Development

This project follows a strict **test-driven development (TDD)** workflow. Every utility and tool was implemented test-first:

1. **Add fixtures** to `tests/fixtures/` — either using the small hand-rolled `mini_spec.py` (fast, deterministic) or the vendored `cin7_v2.json` for contract tests
2. **Write failing tests** — unit tests against the mini spec, contract tests against the real vendored spec where relevant
3. **Implement** to make the tests pass

No new code should be merged without corresponding test coverage. See [CLAUDE.md](CLAUDE.md) for detailed test patterns, the `mock_cin7` fixture, and the `EXPECTED_TOOLS` registration assertion.

### Architecture

- **`cin7_client.py`** - Async REST client for the Cin7 Core API with retry and error handling (ported from `mcp-cin7-core`)
- **`spec_loader.py`** - Loads the vendored normalized JSON catalog at startup, builds the in-memory endpoint and search indexes
- **`spec_parser.py`** - Parses API Blueprint markdown into the normalized JSON catalog (used by `scripts/refresh_spec.py`)
- **`spec_search.py`** - Ranked substring search over the spec index (exact path > prefix > substring > summary/param-name match)
- **`validator.py`** - Validates query params (unknowns, required, types) and body (required fields) against the loaded spec; returns structured error responses instead of raising
- **`issue_reporter.py`** - Single-function entry point for `report_issue` storage — appends one `ISSUE_REPORT <json>` line to a controlled file *and* to stderr
- **`session_store.py`** - In-memory session storage with TTL (ported)
- **`server.py`** - FastMCP server with the four tool registrations
- **`server_http.py`** - Starlette wrapper with MCP Streamable HTTP transport and ScaleKit OAuth (ported)
- **`server_stdio.py`** - Stdio transport for local Claude Desktop integration
- **`resources/`** - Tool implementations (`endpoints.py`, `invoke.py`, `issues.py`)
- **`utils/`** - Shared utilities

See [CLAUDE.md](CLAUDE.md) for comprehensive development documentation, test patterns, and architecture details.

## Security

Do not commit your `.env` file or any Cin7 API credentials to version control (it is included in `.gitignore` as a safe default).

Issue reports written by `report_issue` may contain raw request bodies, query parameters, and response excerpts — review `data/issue_reports.log` before sharing it with anyone outside the project.

## License

MIT
