# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this server is

`mcp-cin7-meta` is the **API-walking** counterpart to the sibling `mcp-cin7-core` server. Instead of exposing one MCP tool per Cin7 Core endpoint, it exposes four generic tools:

- `list_api_endpoints(keyword, methods, limit)` — keyword search across Cin7's endpoint catalog
- `get_api_endpoint_schema(method, path)` — returns the full schema for one endpoint (params, body, response)
- `invoke_api_endpoint(method, path, query_params, body)` — validates, then executes
- `report_issue(...)` — captures structured bug reports for later developer review

The model is expected to chain them: list → read schema → call. Read [docs/tools.md](docs/tools.md) for full signatures and examples.

## Spec source

The server validates and indexes against a **vendored** API Blueprint at `cin7_meta/spec/cin7_v2.apib` plus its derived normalized catalog at `cin7_meta/spec/cin7_v2.json`. To refresh:

```bash
uv run python scripts/refresh_spec.py
```

See [docs/spec_refresh.md](docs/spec_refresh.md) for the workflow and when to refresh.

Source URL: `https://dearinventory.docs.apiary.io/api-description-document`. Override the local path with `CIN7_SPEC_PATH` env var.

## ScaleKit Configuration

Identical setup to `mcp-cin7-core`. Register your server in the ScaleKit dashboard:

1. **MCP Servers > Add MCP Server**
2. Server name: `cin7-meta`; Resource identifier: your server URL; Scopes: `cin7:read`, `cin7:write`
3. Enable dynamic client registration
4. Copy credentials to `.env`: `SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_CLIENT_ID`, `SCALEKIT_CLIENT_SECRET`, `SCALEKIT_RESOURCE_ID`

### Authentication Interceptors

Same email-allowlist pattern as the sibling repo. Two interceptors (`PRE_SIGNUP`, `PRE_SESSION_CREATION`) pointed at:
- `POST /auth/interceptors/pre-signup`
- `POST /auth/interceptors/pre-session-creation`

Set `SCALEKIT_INTERCEPTOR_SECRET` for signature verification, and `ALLOWED_EMAILS` for the allowlist (comma-separated; empty = allow all).

## Testing

### Running Tests

```bash
uv run pytest -v
uv run pytest --tb=short
uv run pytest tests/test_invoke_api_endpoint.py -v
```

### Test Structure

```
tests/
  conftest.py                       # mock_cin7 context manager, mini_spec_index fixtures
  fixtures/
    mini_spec.py                    # hand-rolled small normalized catalog (fast tests)
    mini_apib.py                    # hand-rolled small API Blueprint sample (parser tests)
  test_spec_parser.py               # API Blueprint -> normalized JSON
  test_spec_loader.py               # load + index normalized JSON
  test_spec_search.py               # ranked substring search
  test_validator.py                 # unknowns / required / type coercion
  test_list_api_endpoints.py        # MCP tool wrapper
  test_get_api_endpoint_schema.py   # MCP tool wrapper
  test_invoke_api_endpoint.py       # validation reject, success, 4xx, transport errors
  test_issue_reporter.py            # record_issue() unit tests
  test_report_issue.py              # MCP tool wrapper
  test_cin7_client.py               # retry/auth/error suite (single-tenant)
  test_session_store.py             # ported in-memory session TTL
  test_logging.py                   # truncate() + setup_logging() env reading
  test_errors.py                    # Cin7*Error hierarchy
  test_server.py                    # EXPECTED_TOOLS = {"list_api_endpoints","get_api_endpoint_schema","invoke_api_endpoint","report_issue"}
```

### TDD Workflow

This server follows strict TDD. Adding or changing a tool:

1. **Write the failing test first** in the relevant `tests/test_*.py` — assert the exact behavior you want.
2. **Run it; watch it fail** with `uv run pytest tests/test_<file>.py -v`.
3. **Write the minimal code** to make it pass.
4. **Run the full suite** — `uv run pytest -v` — to catch regressions.
5. **Refactor** while keeping the suite green.

Never write production code before its test exists and fails. Never adapt previously-written code; if you wrote code before the test, delete it.

### Test Patterns

**Spec-walking unit tests** use the small hand-rolled spec in `tests/fixtures/mini_spec.py` — fast, deterministic, no Cin7 dependency.

**Parser tests** use a small hand-rolled API Blueprint sample in `tests/fixtures/mini_apib.py` for fast iteration, plus a few smoke checks against the vendored real Blueprint.

**MCP tool tests** mock the Cin7 client (`mock_cin7` context manager from `conftest.py`) and assert the validator pipeline ran before any network call.

## Architecture

### Core components

**`cin7_meta/utils/cin7_client.py`** — async REST client (ported from `mcp-cin7-core`)
- Per-request `httpx.AsyncClient` (no persistent pool)
- Exponential backoff retry on 429/5xx and network/timeout failures (3 attempts, delays `[1s, 2s, 4s]`)
- Error hierarchy: `Cin7AuthError`, `Cin7NotFoundError`, `Cin7RateLimitError`, `Cin7APIError`
- Auth headers `api-auth-accountid` + `api-auth-applicationkey` from `CIN7_ACCOUNT_ID` + `CIN7_API_KEY`

**`cin7_meta/utils/spec_loader.py`** — module-import-time loader
- Reads `cin7_meta/spec/cin7_v2.json`
- Builds `endpoints_by_key: dict[str, EndpointDef]` and `search_entries: list[SearchEntry]`
- Fails loud at import if file missing/malformed

**`cin7_meta/utils/spec_parser.py`** — API Blueprint markdown → normalized JSON
- Walks markdown headers and `+ Parameters` / `+ Request` / `+ Response` blocks
- Permissive: parsing failures become `parser_warnings` entries, never exceptions
- Used by `scripts/refresh_spec.py` at refresh time

**`cin7_meta/utils/spec_search.py`** — ranked keyword search
- Substring match (case-insensitive) over path, summary, group, param names
- Ranking: exact-path > prefix-path > substring-path > summary/param match
- Honors `methods` filter and `limit`; returns `truncated` flag

**`cin7_meta/utils/validator.py`** — request validation
- `validate_invocation(endpoint, query_params, body) -> list[error_dict]`
- Rejects unknown query-param names; checks required; coerces / type-checks
- Body: strict on required fields, permissive on extras (Cin7 accepts extras)

**`cin7_meta/utils/issue_reporter.py`** — single-function `record_issue(payload)`
- Always: structured `ISSUE_REPORT <json>` log line on stderr (captured by Render's log stream)
- Best-effort: append the same `ISSUE_REPORT <json>` line to `data/issue_reports.log` (configurable via `ISSUE_REPORT_PATH`). Identical format to the stderr line so the same `grep ISSUE_REPORT` works against either source.
- Returns `(report_id, wrote_to_file)`

**`cin7_meta/server.py`** — slim FastMCP registration (4 `mcp.tool()(fn)` calls)

**`cin7_meta/server_http.py`** — Starlette wrapper with ScaleKit OAuth + interceptors + session store (ported, package paths swapped)

**`cin7_meta/server_stdio.py`** — stdio entrypoint with env validation

## Common operations

### Find an endpoint

```python
list_api_endpoints("product")
# → list of endpoints with paths containing "product"

list_api_endpoints("sale", methods=["POST"], limit=10)
# → only POST endpoints in the sale group
```

### Inspect an endpoint before calling it

```python
get_api_endpoint_schema(method="GET", path="Product")
# → query_params (Page, Limit, Sku, ...), response_schema, response_example
```

### Invoke an endpoint

```python
invoke_api_endpoint(
    method="GET",
    path="Product",
    query_params={"Page": 1, "Limit": 50, "Sku": "WIDGET-001"},
)
# Pipeline: lookup → validate query_params → execute
# Returns: {"status": 200, "data": {"Products": [...], "Total": 1}, "rate_limit_remaining": "58"}

invoke_api_endpoint(
    method="POST",
    path="advanced-purchase",
    body={"Supplier": "Acme", "Location": "Main", "Status": "DRAFT", "OrderDate": "2026-05-15"},
)
```

### Report an issue when stuck

```python
report_issue(
    summary="POST /Sale returned 200 but ignored line items",
    tool_name="invoke_api_endpoint",
    tool_arguments={"method": "POST", "path": "Sale", "body": {...}},
    observed_behavior="Returned a sale with empty Lines[]",
    expected_behavior="Should have included the line items I passed in body",
    severity="medium",
)
# Appended to data/issue_reports.log + logged with ISSUE_REPORT prefix.
```

## Development Notes

- The vendored normalized JSON is the canonical spec for both `get_api_endpoint_schema` and `invoke_api_endpoint` validation. The raw `.apib` is kept alongside for diffing/debugging.
- `invoke_api_endpoint` does NOT strip Cin7 IDs in responses — raw passthrough so the model can use IDs in follow-up calls.
- All issue reports include a generated `report_id` (`rpt_<hex8>`) — quote it back to the user when filing reports.
- Sensitive headers (`api-auth-accountid`, `api-auth-applicationkey`, `Authorization`) are redacted in logs by the Cin7 client.
- MCP Streamable HTTP transport supports both batch and streaming response modes via FastMCP.
- Cin7's API uses query strings for resource selection (`?ID=...`, `?TaskID=...`, `?Sku=...`). There is no path-segment templating in `invoke_api_endpoint`.
