# Testing Guide

## Prerequisites

1. Cin7 Core (DEAR) account with `AccountID` and `Application Key`
2. `.env` file with `CIN7_ACCOUNT_ID` and `CIN7_API_KEY` configured
3. Vendored spec present at `cin7_meta/spec/cin7_v2.json` (run `scripts/refresh_spec.py` once)

## Automated Tests

```bash
uv run pytest -v                                       # full suite
uv run pytest --tb=short                               # quick pass/fail
uv run pytest tests/test_invoke_api_endpoint.py -v     # one file
```

## Manual Testing Checklist

### `list_api_endpoints`
- [ ] Exact path match returns it first (e.g. `Product` ranks above `product-suppliers`)
- [ ] Substring match across summaries (e.g. `stock` finds `stockTransfer`, `stockadjustment`, `ref/productavailability`)
- [ ] `methods=["POST"]` filter restricts results to mutating endpoints
- [ ] `limit` honored, `truncated` flag set when results exceed limit
- [ ] Empty keyword returns a structured error, not a crash
- [ ] Unicode / special characters don't break the search

### `get_api_endpoint_schema`
- [ ] Returns the endpoint's own param list, body schema, response schema/example
- [ ] Both `"Product"` and `"/Product"` resolve to the same endpoint (path normalization)
- [ ] Method casing is normalized (`get` / `GET` / `Get` all work)
- [ ] Unknown (method, path) returns a structured error including a `did_you_mean` suggestion if close

### `invoke_api_endpoint`
- [ ] Valid GET executes and returns `{status, data, rate_limit_remaining}`
- [ ] Unknown endpoint returns structured error, **no network call made**
- [ ] Unknown query param returns structured error, **no network call made**
- [ ] Missing required query param returns structured error, **no network call made**
- [ ] Type mismatch on query param returns structured error, **no network call made**
- [ ] Missing required body field returns structured error, **no network call made**
- [ ] Cin7 4xx returns `{status: 4xx, data: <body or null>, errors: [...]}`
- [ ] Cin7 200 with valid response data returns `{status: 200, data: {...}}`
- [ ] `rate_limit_remaining` reflects the `X-RateLimit-Remaining` response header

### `report_issue`
- [ ] Missing required field (summary, tool_name, tool_arguments, observed, expected) is rejected
- [ ] Successful report returns `report_id` matching `rpt_[0-9a-f]{8}`
- [ ] Log file gets a new `ISSUE_REPORT <json>` line with all fields + timestamp + server_version + python_version
- [ ] Same line appears on stderr (Render log stream in prod)
- [ ] If log path is unwritable, response still returns `report_id` with `stored_in_file=False`; stderr line still emitted
