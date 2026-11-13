"""Load and index a normalized Cin7 Core spec catalog.

The catalog written by `cin7-meta-refresh-spec` (see `cin7_meta/cli/refresh_spec.py`)
ships in the package at `cin7_meta/spec/cin7_v2.json`. This module loads it
lazily and builds two in-memory indexes:

- `endpoints_by_key`: `"METHOD path"` -> `EndpointDef`
- `search_entries`: flat list used by `spec_search` for ranked lookup

Which file is loaded (first match wins, see `resolve_spec_path`):

1. `CIN7_SPEC_PATH` — an explicit catalog *file*, used as-is.
2. `CIN7_SPEC_DIR`  — a *directory* holding `cin7_v2.json` (where
   `cin7-meta-refresh-spec` writes when the var is set), if that file exists.
3. The catalog shipped inside the package.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SPEC_FILENAME = "cin7_v2.json"
SPEC_DIR = Path(__file__).resolve().parent.parent / "spec"
DEFAULT_SPEC_PATH = SPEC_DIR / SPEC_FILENAME
REFRESH_COMMAND = "cin7-meta-refresh-spec"


def spec_dir_from_env() -> Path | None:
    """The `CIN7_SPEC_DIR` directory (with `~` expanded), or None if unset."""
    raw = os.getenv("CIN7_SPEC_DIR", "").strip()
    return Path(raw).expanduser() if raw else None


def resolve_spec_path() -> Path:
    """Pick the catalog file to load: CIN7_SPEC_PATH > CIN7_SPEC_DIR > packaged.

    Raises FileNotFoundError naming every path checked when no catalog exists.
    """
    explicit = os.getenv("CIN7_SPEC_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    checked: list[Path] = []
    spec_dir = spec_dir_from_env()
    if spec_dir is not None:
        candidate = spec_dir / SPEC_FILENAME
        if candidate.is_file():
            return candidate
        checked.append(candidate)
        logger.warning(
            "CIN7_SPEC_DIR is set but %s does not exist; falling back to the "
            "packaged spec. Run `%s` to populate it.",
            candidate,
            REFRESH_COMMAND,
        )

    if DEFAULT_SPEC_PATH.is_file():
        return DEFAULT_SPEC_PATH
    checked.append(DEFAULT_SPEC_PATH)

    raise FileNotFoundError(
        "No Cin7 spec catalog found. Checked: "
        + ", ".join(str(p) for p in checked)
        + f". Generate one with `{REFRESH_COMMAND}` (writes to CIN7_SPEC_DIR when "
        "set), or point CIN7_SPEC_PATH at an existing catalog file."
    )


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

    The file comes from `resolve_spec_path()`. Fails loud if it is missing or
    malformed.
    """
    global _spec
    if _spec is None:
        path = str(resolve_spec_path())
        logger.info("Loading Cin7 spec from %s", path)
        _spec = load_spec_from_path(path)
        logger.info(
            "Spec loaded: %d endpoints, base_url=%s",
            len(_spec.endpoints_by_key),
            _spec.base_url,
        )
    return _spec
