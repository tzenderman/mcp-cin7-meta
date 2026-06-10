"""MCP tool: invoke_api_endpoint.

Pipeline:

1. Resolve (method, path) against the vendored spec.
2. Validate query params (unknown / required / type).
3. Validate body (required fields).
4. Execute via the shared `Cin7Client.invoke()`.
5. Return `{"status", "data", "rate_limit_remaining"}` on 2xx; on 4xx
   include `errors` for the model to read.

Validation failures (1-3) never make a network call — the model gets the
error structure synchronously and can fix the call.
"""

from __future__ import annotations

import logging
from typing import Any

from cin7_meta.utils.cin7_client import get_cin7_client
from cin7_meta.utils.spec_loader import get_spec
from cin7_meta.utils.validator import validate_invocation

logger = logging.getLogger(__name__)


async def invoke_api_endpoint(
    method: str,
    path: str,
    query_params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, then execute, a Cin7 Core REST API call.

    Args:
        method: HTTP verb (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`).
            Case-insensitive.
        path: Endpoint path, e.g. `"Product"`, `"advanced-purchase"`,
            `"sale/order"`. Leading slashes are stripped.
        query_params: Query-string parameters. Validated against the
            endpoint's declared params.
        body: JSON request body. Validated against the endpoint's required
            body fields (extras are permitted).

    Returns:
        Success: `{"status": 200, "data": <json>, "rate_limit_remaining": "59"}`.
        Cin7 4xx response: `{"status": 4xx, "data": <body or null>, "errors": [...]}`.
        Validation failure: `{"status": null, "data": null, "errors": [...]}`.

    Raises:
        Cin7AuthError | Cin7NotFoundError | Cin7RateLimitError | Cin7APIError:
            Transport-level failures the model cannot fix.
    """
    logger.debug(
        "invoke_api_endpoint method=%s path=%s qp_count=%d has_body=%s",
        method,
        path,
        len(query_params or {}),
        body is not None,
    )

    spec = get_spec()
    endpoint = spec.get_endpoint(method, path)
    if endpoint is None:
        return {
            "status": None,
            "data": None,
            "errors": [
                {
                    "message": (
                        f"Endpoint {method.upper()} /{path.lstrip('/')} not found in spec. "
                        f"Use list_api_endpoints to find a valid endpoint."
                    )
                }
            ],
        }

    validation_errors = validate_invocation(endpoint, query_params, body)
    if validation_errors:
        return {"status": None, "data": None, "errors": validation_errors}

    client = get_cin7_client()
    status, data, headers = await client.invoke(
        endpoint.method,
        endpoint.path,
        query_params=query_params,
        body=body,
    )

    result: dict[str, Any] = {
        "status": status,
        "data": data,
        "rate_limit_remaining": headers.get("X-RateLimit-Remaining"),
    }
    if 400 <= status < 500:
        # Surface 4xx errors so the model can adjust the call.
        message = f"Cin7 returned HTTP {status}"
        if isinstance(data, list) and data and isinstance(data[0], dict):
            exc = data[0].get("Exception") or data[0].get("Message")
            if exc:
                message = f"{message}: {exc}"
        elif isinstance(data, dict):
            exc = data.get("Exception") or data.get("Message") or data.get("error")
            if exc:
                message = f"{message}: {exc}"
        result["errors"] = [{"message": message}]

    return result
