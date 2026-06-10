"""Load and index a normalized Cin7 Core spec catalog.

The result of `scripts/refresh_spec.py` is expected to live at
`cin7_meta/spec/cin7_v2.json`. This module loads it lazily and builds two
in-memory indexes:

- `endpoints_by_key`: `"METHOD path"` -> `EndpointDef`
- `search_entries`: flat list used by `spec_search` for ranked lookup

The default path can be overridden with the `CIN7_SPEC_PATH` env var.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SPEC_DIR = Path(__file__).resolve().parent.parent / "spec"
DEFAULT_SPEC_PATH = SPEC_DIR / "cin7_v2.json"


def _normalize_key(method: str, path: str) -> str:
    return f"{method.upper().strip()} {path.lstrip('/').strip()}"


@dataclass(frozen=True)
class ParamDef:
    name: str
    type: str
    required: bool
    default: Any | None
    description: str | None


@dataclass(frozen=True)
class EndpointDef:
    method: str
    path: str
    group: str
    summary: str
    description: str
    query_params: tuple[ParamDef, ...]
    request_body_schema: dict | None
    request_body_example: dict | None
    response_schema: dict | None
    response_example: Any | None

    @property
    def key(self) -> str:
        return _normalize_key(self.method, self.path)


@dataclass(frozen=True)
class SpecIndex:
    raw: dict
    base_url: str
    endpoints_by_key: dict[str, EndpointDef]
    search_entries: tuple[EndpointDef, ...]

    def get_endpoint(self, method: str, path: str) -> EndpointDef | None:
        return self.endpoints_by_key.get(_normalize_key(method, path))


def _build_endpoint(raw_endpoint: dict) -> EndpointDef:
    params = tuple(
        ParamDef(
            name=p["name"],
            type=p.get("type", "string"),
            required=bool(p.get("required", False)),
            default=p.get("default"),
            description=p.get("description"),
        )
        for p in raw_endpoint.get("query_params") or []
    )
    return EndpointDef(
        method=raw_endpoint["method"].upper(),
        path=raw_endpoint["path"].lstrip("/").strip(),
        group=raw_endpoint.get("group", ""),
        summary=raw_endpoint.get("summary", ""),
        description=raw_endpoint.get("description", ""),
        query_params=params,
        request_body_schema=raw_endpoint.get("request_body_schema"),
        request_body_example=raw_endpoint.get("request_body_example"),
        response_schema=raw_endpoint.get("response_schema"),
        response_example=raw_endpoint.get("response_example"),
    )


def load_spec_from_dict(catalog: dict) -> SpecIndex:
    if "endpoints" not in catalog:
        raise ValueError("catalog is missing required 'endpoints' key")

    endpoints = [_build_endpoint(e) for e in catalog["endpoints"]]
    endpoints_by_key = {e.key: e for e in endpoints}

    return SpecIndex(
        raw=catalog,
        base_url=catalog.get("base_url", ""),
        endpoints_by_key=endpoints_by_key,
        search_entries=tuple(endpoints),
    )


def load_spec_from_path(path: str) -> SpecIndex:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"spec file not found at {path}")

    try:
        with open(p) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed spec JSON at {path}: {e}")

    return load_spec_from_dict(data)


_spec: SpecIndex | None = None


def get_spec() -> SpecIndex:
    """Return the cached SpecIndex, loading on first call.

    Reads `CIN7_SPEC_PATH` env var if set, otherwise resolves the default
    `cin7_meta/spec/cin7_v2.json`. Fails loud if the file is missing or
    malformed.
    """
    global _spec
    if _spec is None:
        path = os.getenv("CIN7_SPEC_PATH") or str(DEFAULT_SPEC_PATH)
        logger.info("Loading Cin7 spec from %s", path)
        _spec = load_spec_from_path(path)
        logger.info(
            "Spec loaded: %d endpoints, base_url=%s",
            len(_spec.endpoints_by_key),
            _spec.base_url,
        )
    return _spec
