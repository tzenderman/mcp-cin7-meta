"""Ranked keyword search over the Cin7 spec index.

Mirrors the shape of `shopify_meta/utils/schema_search.py`: same return
dict, same ordering bias (exact > prefix > substring > description-only).
"""

from __future__ import annotations

from typing import Any

from .spec_loader import EndpointDef, SpecIndex


_RANK_EXACT_PATH = 0
_RANK_PREFIX_PATH = 1
_RANK_SUBSTRING_PATH = 2
_RANK_SUMMARY = 3
_RANK_GROUP = 4
_RANK_PARAM = 5
_RANK_NONE = 99


def _score(endpoint: EndpointDef, keyword_lower: str) -> int:
    path_lower = endpoint.path.lower()
    if path_lower == keyword_lower:
        return _RANK_EXACT_PATH
    if path_lower.startswith(keyword_lower):
        return _RANK_PREFIX_PATH
    if keyword_lower in path_lower:
        return _RANK_SUBSTRING_PATH
    if keyword_lower in (endpoint.summary or "").lower():
        return _RANK_SUMMARY
    if keyword_lower in (endpoint.group or "").lower():
        return _RANK_GROUP
    for p in endpoint.query_params:
        if keyword_lower in p.name.lower():
            return _RANK_PARAM
    return _RANK_NONE


def search_spec_index(
    spec: SpecIndex,
    keyword: str,
    methods: list[str] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Return endpoints matching `keyword`, ranked by quality of match.

    Args:
        spec: A loaded `SpecIndex`.
        keyword: Substring to look for. Case-insensitive. Required.
        methods: Optional list of HTTP methods to filter to. Case-insensitive.
        limit: Maximum number of results to return.

    Returns:
        `{"results": [{"method","path","summary","group"}, ...],
          "total": int, "truncated": bool}`.
        Empty keyword returns the same shape plus an `error` key.
    """
    if not keyword or not keyword.strip():
        return {"results": [], "total": 0, "truncated": False, "error": "keyword is required."}

    keyword_lower = keyword.strip().lower()
    method_set = {m.upper().strip() for m in methods} if methods else None

    scored: list[tuple[int, str, EndpointDef]] = []
    for endpoint in spec.search_entries:
        if method_set and endpoint.method not in method_set:
            continue
        rank = _score(endpoint, keyword_lower)
        if rank == _RANK_NONE:
            continue
        # Secondary sort key: path alphabetically for stable ordering.
        scored.append((rank, endpoint.path.lower(), endpoint))

    scored.sort(key=lambda t: (t[0], t[1]))

    total = len(scored)
    truncated = total > limit
    results = [
        {
            "method": e.method,
            "path": e.path,
            "summary": e.summary,
            "group": e.group,
        }
        for _, _, e in scored[:limit]
    ]
    return {"results": results, "total": total, "truncated": truncated}
