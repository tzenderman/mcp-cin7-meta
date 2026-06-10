"""MCP tools for walking the Cin7 Core REST API catalog.

- `list_api_endpoints` — keyword search across paths, summaries, groups, params.
- `get_api_endpoint_schema` — return the full schema for one endpoint.

Both delegate to `utils.spec_loader` + `utils.spec_search`.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from cin7_meta.utils.spec_loader import EndpointDef, SpecIndex, get_spec
from cin7_meta.utils.spec_search import search_spec_index

logger = logging.getLogger(__name__)


async def list_api_endpoints(
    keyword: str,
    methods: list[str] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Search Cin7 Core's REST endpoints by keyword.

    Args:
        keyword: Substring to match against path, summary, group, and
            parameter names. Case-insensitive.
        methods: Optional list of HTTP methods to restrict results to.
            Valid values: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`.
        limit: Maximum number of results to return. Default 25.

    Returns:
        `{"results": [{"method","path","summary","group"}, ...],
          "total": int, "truncated": bool}`.
        On empty keyword, returns the same shape with an additional `error` key.
    """
    logger.debug("list_api_endpoints keyword=%r methods=%r limit=%d", keyword, methods, limit)
    try:
        return search_spec_index(get_spec(), keyword=keyword, methods=methods, limit=limit)
    except ValueError as e:
        return {"results": [], "total": 0, "truncated": False, "error": str(e)}


def _serialize_endpoint(endpoint: EndpointDef) -> dict[str, Any]:
    return {
        "method": endpoint.method,
        "path": endpoint.path,
        "group": endpoint.group,
        "summary": endpoint.summary,
        "description": endpoint.description,
        "query_params": [asdict(p) for p in endpoint.query_params],
        "request_body_schema": endpoint.request_body_schema,
        "request_body_example": endpoint.request_body_example,
        "response_schema": endpoint.response_schema,
        "response_example": endpoint.response_example,
    }


def _suggest(spec: SpecIndex, method: str, path: str) -> str | None:
    """Best single suggestion for an unknown (method, path)."""
    target = path.lstrip("/").strip().lower()
    method_upper = method.upper().strip()
    candidates = list(spec.endpoints_by_key.values())

    # Exact path, any method
    for e in candidates:
        if e.path.lower() == target and e.method != method_upper:
            return f"{e.method} {e.path}"

    # Substring match within same method
    for e in candidates:
        if e.method == method_upper and target in e.path.lower():
            return f"{e.method} {e.path}"

    # Substring match across methods
    for e in candidates:
        if target in e.path.lower():
            return f"{e.method} {e.path}"

    return None


async def get_api_endpoint_schema(method: str, path: str) -> dict[str, Any]:
    """Return the full schema for one Cin7 API endpoint.

    Args:
        method: HTTP verb. Case-insensitive.
        path: Endpoint path. Leading slashes are stripped; the lookup is
            case-sensitive on the path itself.

    Returns:
        `{"method","path","group","summary","description",
          "query_params","request_body_schema","request_body_example",
          "response_schema","response_example"}`.
        On unknown endpoint, returns `{"error": "..."}` with a `did_you_mean`
        hint if a close match exists.
    """
    spec = get_spec()
    endpoint = spec.get_endpoint(method, path)
    if endpoint is None:
        suggestion = _suggest(spec, method, path)
        msg = f"Endpoint {method.upper()} /{path.lstrip('/')} not found in spec."
        if suggestion:
            msg += f" Did you mean '{suggestion}'?"
        return {"error": msg, "did_you_mean": suggestion}
    return _serialize_endpoint(endpoint)
