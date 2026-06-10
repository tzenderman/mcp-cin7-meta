# Refreshing the vendored API Blueprint

The MCP server validates and indexes against a vendored copy of Cin7 Core's API Blueprint at `cin7_meta/spec/cin7_v2.apib`, plus a derived normalized JSON catalog at `cin7_meta/spec/cin7_v2.json`. Both ship in this repo so a fresh clone works without a network call.

## When to refresh

- **Cin7 adds new endpoints** or new query params on existing endpoints
- **Cin7 changes parameter names, types, or required-ness**
- You notice `parser_warnings` referencing endpoints you care about

There's no version pin — the Apiary publication is rolling. Refresh whenever you suspect drift.

## How to refresh

From a fresh clone:

```bash
uv venv
uv pip install -e .
uv run python scripts/refresh_spec.py
```

The script:

1. Fetches `https://dearinventory.docs.apiary.io/api-description-document` (publicly readable; no credentials needed)
2. Writes the raw markdown to `cin7_meta/spec/cin7_v2.apib`
3. Parses it via `cin7_meta/utils/spec_parser.py` into `cin7_meta/spec/cin7_v2.json`
4. Logs the endpoint count and any parser warnings

Pass `--no-fetch` to re-parse the existing `.apib` without a network call (useful when iterating on the parser itself):

```bash
uv run python scripts/refresh_spec.py --no-fetch
```

## What lives in the catalog

```json
{
  "version": "v2",
  "base_url": "https://inventory.dearsystems.com/ExternalApi/v2/",
  "generated_at": "2026-05-15T...Z",
  "source": "https://dearinventory.docs.apiary.io/api-description-document",
  "endpoints": [ ... 200+ entries ... ],
  "parser_warnings": [ {"section": "...", "reason": "..."} ]
}
```

Each endpoint entry:

```json
{
  "method": "GET",
  "path": "product",
  "group": "Product",
  "summary": "List products",
  "description": "...",
  "query_params": [
    {"name": "Page", "type": "integer", "required": false, "default": 1}
  ],
  "request_body_schema": null,
  "request_body_example": null,
  "response_schema": { ... },
  "response_example": { ... }
}
```

## Parser warnings

The parser is permissive: anything it can't reliably interpret becomes a warning in the JSON catalog rather than an exception. Typical warning reasons:

- `could not parse response body as JSON` — the API Blueprint sample has trailing commas, comments, or other JSON-with-extensions that `json.loads` rejects
- `could not parse request body as JSON` — same, for POST/PUT request samples
- `unknown HTTP method 'X'` — the action header has an unrecognized verb

When a warning matters (the endpoint is real and you need its body schema), hand-edit `cin7_meta/spec/cin7_v2.json` directly. Don't commit fixes to `cin7_v2.apib` — that file should mirror the upstream Apiary content.

## Verifying after refresh

```bash
uv run pytest -v
```

The `tests/test_spec_loader.py::test_real_vendored_spec_loads` test asserts the vendored catalog loads and has at least 100 endpoints. If you broke parsing, this fails.

## Where the path lookup is case-sensitive

The catalog stores paths as Cin7 documents them — typically lowercase (`product`, `customer`, `saleList`). The lookup in `spec_loader.get_endpoint(method, path)` strips a leading `/` but preserves case. So the model should refer to endpoints by their exact catalog case (use `list_api_endpoints` to discover the canonical form). Cin7's server is actually case-insensitive in URLs, but the spec is the source of truth for what the model can call.
