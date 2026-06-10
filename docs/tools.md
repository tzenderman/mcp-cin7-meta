# Tools

This server exposes four MCP tools. The first three let the LLM walk the Cin7 Core REST API at runtime; the fourth captures bug reports for the developer.

---

## `list_api_endpoints(keyword, methods=None, limit=25)`

Find Cin7 Core REST endpoints by keyword.

### Parameters

| Name | Type | Required | Description |
|---|---|:-:|---|
| `keyword` | string | yes | Case-insensitive substring matched against endpoint path, summary, group, and parameter names. |
| `methods` | string[] | no | Restrict to one or more of: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. |
| `limit` | int | no | Default 25. Set higher to scan more matches. |

### Returns

```json
{
  "results": [
    {"method": "GET",  "path": "product",          "summary": "List products",  "group": "Product"},
    {"method": "POST", "path": "product",          "summary": "Create product", "group": "Product"},
    {"method": "GET",  "path": "product-suppliers","summary": "Get suppliers",  "group": "Reference Books"}
  ],
  "total": 12,
  "truncated": false
}
```

Ranking, best first: exact path match → path prefix → path substring → summary match → group match → param-name match. Within a tier, results are sorted alphabetically so output is stable.

### Examples

```python
list_api_endpoints("product")
list_api_endpoints("sale", methods=["POST"], limit=10)
list_api_endpoints("stock", methods=["GET"])
```

---

## `get_api_endpoint_schema(method, path)`

Return the full schema for one endpoint — query params, request body, response body, examples.

### Parameters

| Name | Type | Required | Description |
|---|---|:-:|---|
| `method` | string | yes | HTTP verb. Case-insensitive. |
| `path` | string | yes | Endpoint path (e.g. `product`, `advanced-purchase`, `sale/order`). Leading slashes are stripped. |

### Returns

```json
{
  "method": "GET",
  "path": "product",
  "group": "Product",
  "summary": "List products",
  "description": "Returns a paginated list of products.",
  "query_params": [
    {"name": "Page",  "type": "integer", "required": false, "default": 1,   "description": "Page number"},
    {"name": "Limit", "type": "integer", "required": false, "default": 100, "description": "Page size"},
    {"name": "Sku",   "type": "string",  "required": false, "default": null,"description": "Filter by SKU"}
  ],
  "request_body_schema": null,
  "request_body_example": null,
  "response_schema": {"type": "object", "properties": {"Products": {"type": "array"}, "Total": {"type": "integer"}}},
  "response_example": {"Products": [{"ID": "...", "SKU": "..."}], "Total": 1}
}
```

### Examples

```python
get_api_endpoint_schema(method="GET", path="product")
get_api_endpoint_schema(method="POST", path="advanced-purchase")
```

### Error handling

Unknown (method, path) returns `{"error": "Endpoint X not found...", "did_you_mean": "GET product"}` with a closest-match suggestion. Never throws.

---

## `invoke_api_endpoint(method, path, query_params=None, body=None)`

Validate and execute a Cin7 Core REST request.

### Parameters

| Name | Type | Required | Description |
|---|---|:-:|---|
| `method` | string | yes | HTTP verb (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`). Case-insensitive. |
| `path` | string | yes | Endpoint path. Leading slashes are stripped. |
| `query_params` | object | no | Query-string parameters. Validated against the endpoint's declared params. |
| `body` | object | no | JSON request body. Validated against the endpoint's required body fields (extras permitted). |

### Pipeline

The call is rejected before any network round-trip if:
1. The (method, path) pair is **unknown** in the vendored spec.
2. `query_params` contains **unknown names**.
3. A **required** query param is missing.
4. A query param has the **wrong type** (e.g. `Page="not-an-int"` for an integer field).
5. For methods with a documented request body schema, a **required body field** is missing.

In all five cases, the response is `{"status": null, "data": null, "errors": [{"message", "field"?}]}`.

### Returns

```json
{
  "status": 200,
  "data": {"Products": [...], "Total": 1},
  "rate_limit_remaining": "58"
}
```

For Cin7-returned 4xx responses (e.g. validation failures on the server side):

```json
{
  "status": 400,
  "data": [{"Exception": "Bad SKU format"}],
  "errors": [{"message": "Cin7 returned HTTP 400: Bad SKU format"}],
  "rate_limit_remaining": "57"
}
```

Use `rate_limit_remaining` to self-pace successive calls. Cin7 limits to 60 requests/minute.

### Exceptions (transport-level)

These bubble up as `ToolError` to the MCP client — the model cannot fix them by adjusting the request:

- `Cin7AuthError` — bad creds (no retry)
- `Cin7NotFoundError` — endpoint not found at server (no retry)
- `Cin7RateLimitError` — 429s after exhausted retries
- `Cin7APIError` — 5xx after exhausted retries, network failures, JSON parse failures

### Examples

```python
invoke_api_endpoint(
    method="GET",
    path="product",
    query_params={"Sku": "WIDGET-001", "Limit": 1},
)

invoke_api_endpoint(
    method="POST",
    path="advanced-purchase",
    body={
        "Supplier": "Acme",
        "Location": "Main",
        "Status": "DRAFT",
        "OrderDate": "2026-05-15",
    },
)
```

---

## `report_issue(...)`

File a structured bug report when one of the other three tools doesn't behave as expected.

### Parameters

| Name | Type | Required | Description |
|---|---|:-:|---|
| `summary` | string | yes | One-line headline. |
| `tool_name` | string | yes | `list_api_endpoints`, `get_api_endpoint_schema`, or `invoke_api_endpoint`. |
| `tool_arguments` | object | yes | Exact kwargs you passed. Enough for someone else to reproduce the call. |
| `observed_behavior` | string | yes | What actually happened. |
| `expected_behavior` | string | yes | What should have happened. |
| `severity` | string | no | `low`, `medium` (default), `high`. |
| `error_message` | string | no | Exception class + message, if any. |
| `response_excerpt` | string | no | Truncated snippet of the response (auto-clipped to 2000 chars). |
| `client_context` | string | no | Model name, conversation topic, anything that helps repro. |

### Returns

```json
{
  "report_id": "rpt_a3f2c9d1",
  "stored_in_file": true,
  "stored_in_log": true,
  "thanks": "Issue rpt_a3f2c9d1 logged. The developer will review and follow up. ..."
}
```

### Storage

Each report is written as a single structured `ISSUE_REPORT <json>` line to **two sinks** (so nothing is lost in either dev or prod):

1. `data/issue_reports.log` (override path via `ISSUE_REPORT_PATH`). Append-only — one report per line, prefixed with `ISSUE_REPORT `.
2. The same line emitted at INFO level to the module logger. Captured by Render's log stream (and any other stderr-capturing host) regardless of filesystem persistence.

If the file write fails (ephemeral filesystem, perms), `stored_in_file` returns `false` but the log line is still emitted and `report_id` is still returned — the report is never lost.

To review reports as a developer:

```bash
grep "ISSUE_REPORT" data/issue_reports.log | tail -n 20 | sed 's/^ISSUE_REPORT //' | jq .   # local
grep "ISSUE_REPORT" /var/log/render-service.log                                              # production
```
