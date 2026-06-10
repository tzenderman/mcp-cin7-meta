"""Parse the Cin7 Core API Blueprint markdown into a normalized JSON catalog.

The Apiary publication at `https://dearinventory.docs.apiary.io/api-description-document`
is API Blueprint format 1A. This parser walks that markdown looking for the
structural conventions used throughout the document:

  # Group <Group Name>
  ## <Resource Name> [/<resource path>]
  ### <Action Label> [<METHOD>]                # method-only header
  ### <Action Label> [<METHOD> /<full path>]   # method + inline path
  + Parameters
      + <Name> (optional|required, type) ... description
          + Default: <value>
  + Request (application/json)
      + Body
              <JSON body content>
  + Response <code> (application/json)
      + Body
              <JSON body content>
      + Schema
              <JSON schema content>

Permissive philosophy: anything the parser can't reliably interpret becomes a
`parser_warnings` entry, not an exception. The catalog still ships and the
malformed section is skipped.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


_HOST_RE = re.compile(r"^HOST:\s*(\S+)", re.MULTILINE)
_GROUP_RE = re.compile(r"^# Group (.+?)\s*$")
_RESOURCE_RE = re.compile(r"^## (.+?)\s*\[(.+?)\]\s*$")
_ACTION_RE = re.compile(r"^### (.+?)\s*\[(.+?)\]\s*$")
_PARAM_RE = re.compile(
    r"""^\s*\+\s+
        (?P<name>[A-Za-z_][A-Za-z0-9_]*)
        \s*
        (?:\(
            (?P<modifiers>[^)]*)
        \))?
        \s*
        (?:(?:\.\.\.|-)\s*(?P<description>.*?))?
        \s*$""",
    re.VERBOSE,
)
_DEFAULT_RE = re.compile(r"^\s*\+\s+Default:\s*(.+?)\s*$")
_INLINE_DEFAULT_RE = re.compile(r"\(\s*Default:\s*([^)]+?)\s*\)\s*$", re.IGNORECASE)


def _strip_path_template(path: str) -> str:
    """Normalize a resource path: remove leading slash and `{?Page,Limit}` query templates."""
    path = path.strip()
    # Strip URI templates like {?Page,Limit,Sku} or {/id}
    path = re.sub(r"\{[?/&].*?\}", "", path)
    # Strip query strings entirely (`?ID={ID}&Page=...`)
    path = path.split("?", 1)[0]
    return path.lstrip("/").strip()


def _normalize_type(modifier_type: str | None, sample_value: Any) -> str:
    """Map API Blueprint type names to the catalog's normalized types."""
    if modifier_type:
        t = modifier_type.strip().lower()
        if t in {"number", "decimal", "double", "float"}:
            return "integer" if isinstance(sample_value, int) and not isinstance(sample_value, bool) else "number"
        if t == "boolean":
            return "boolean"
        if t == "string":
            return "string"
        if t in {"integer", "int"}:
            return "integer"
    # Default to string
    return "string"


def _parse_default(raw: str) -> Any:
    """Best-effort parse of a default value string into JSON-y python."""
    raw = raw.strip()
    # Try JSON first (covers numbers, booleans, null, strings with quotes)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    # Try plain int
    try:
        return int(raw)
    except ValueError:
        pass
    # Try plain float
    try:
        return float(raw)
    except ValueError:
        pass
    # Strip surrounding quotes if present
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        return raw[1:-1]
    return raw


def _infer_schema(value: Any) -> dict:
    """Infer a shallow JSON schema from a parsed JSON value (best-effort)."""
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {k: _infer_schema(v) for k, v in value.items()},
        }
    if isinstance(value, list):
        items_schema = _infer_schema(value[0]) if value else {"type": "string"}
        return {"type": "array", "items": items_schema}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if value is None:
        return {"type": "null"}
    return {"type": "string"}


def _collect_indented_block(lines: list[str], start: int, min_indent: int) -> tuple[list[str], int]:
    """Collect consecutive lines indented at least `min_indent` spaces.

    Returns (block_lines, next_index). Blank lines inside the block are kept.
    Stops at the first non-blank line indented less than `min_indent`.
    """
    block: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            block.append(line)
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent < min_indent:
            break
        block.append(line)
        i += 1
    # Trim trailing blank lines from the block
    while block and not block[-1].strip():
        block.pop()
    return block, i


def _parse_json_block(block_lines: list[str]) -> Any | None:
    """Try to parse a block of indented lines as JSON. Returns None on failure."""
    if not block_lines:
        return None
    # Dedent: strip the minimum leading whitespace common to all non-empty lines.
    nonblank = [ln for ln in block_lines if ln.strip()]
    if not nonblank:
        return None
    min_indent = min(len(ln) - len(ln.lstrip(" ")) for ln in nonblank)
    dedented = "\n".join(ln[min_indent:] if ln.strip() else "" for ln in block_lines)
    try:
        return json.loads(dedented)
    except (json.JSONDecodeError, ValueError):
        return None


def parse_apib(text: str) -> dict:
    """Parse an API Blueprint markdown document into a normalized catalog dict.

    Returns:
        ```
        {
            "base_url": str,
            "endpoints": [
                {
                    "method": "GET", "path": "Product", "group": "Product",
                    "summary": "...", "description": "...",
                    "query_params": [{"name", "type", "required", "default", "description"}],
                    "request_body_schema": dict | None,
                    "request_body_example": dict | None,
                    "response_schema": dict | None,
                    "response_example": dict | None,
                }, ...
            ],
            "parser_warnings": [{"section": "...", "reason": "..."}],
        }
        ```
    """
    catalog: dict[str, Any] = {
        "base_url": "",
        "endpoints": [],
        "parser_warnings": [],
    }

    host_match = _HOST_RE.search(text)
    if host_match:
        host = host_match.group(1).strip()
        if not host.endswith("/"):
            host = host + "/"
        catalog["base_url"] = host

    lines = text.splitlines()

    current_group: str | None = None
    current_resource_path: str | None = None
    pending: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal pending
        if pending is None:
            return
        # Drop scratchpad keys
        pending.pop("_section", None)
        catalog["endpoints"].append(pending)
        pending = None

    i = 0
    while i < len(lines):
        line = lines[i]

        group_m = _GROUP_RE.match(line)
        if group_m:
            flush()
            current_group = group_m.group(1).strip()
            current_resource_path = None
            i += 1
            continue

        resource_m = _RESOURCE_RE.match(line)
        if resource_m and current_group is not None:
            flush()
            current_resource_path = _strip_path_template(resource_m.group(2))
            i += 1
            continue

        action_m = _ACTION_RE.match(line)
        if action_m and current_group is not None:
            flush()
            label = action_m.group(1).strip()
            bracket = action_m.group(2).strip()
            parts = bracket.split(None, 1)
            method = parts[0].upper()
            if len(parts) == 2:
                path = _strip_path_template(parts[1])
            elif current_resource_path:
                path = current_resource_path
            else:
                catalog["parser_warnings"].append({
                    "section": f"{current_group} / {label}",
                    "reason": "action header has method but no path and no enclosing resource",
                })
                i += 1
                continue

            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                catalog["parser_warnings"].append({
                    "section": f"{current_group} / {label}",
                    "reason": f"unknown HTTP method {method!r}",
                })
                i += 1
                continue

            pending = {
                "method": method,
                "path": path,
                "group": current_group,
                "summary": label,
                "description": "",
                "query_params": [],
                "request_body_schema": None,
                "request_body_example": None,
                "response_schema": None,
                "response_example": None,
                "_section": "",
            }
            i += 1
            continue

        if pending is None:
            i += 1
            continue

        stripped = line.strip()

        # Section detection
        if stripped.startswith("+ Parameters"):
            pending["_section"] = "parameters"
            i += 1
            continue

        if stripped.startswith("+ Request"):
            pending["_section"] = "request"
            i += 1
            continue

        if re.match(r"\+ Response\b", stripped):
            pending["_section"] = "response"
            i += 1
            continue

        if stripped.startswith("+ Body"):
            # Collect JSON body block: must be indented further than `+ Body` itself.
            body_indent = len(line) - len(line.lstrip(" "))
            block, next_i = _collect_indented_block(lines, i + 1, body_indent + 4)
            parsed = _parse_json_block(block)
            section = pending.get("_section")
            if parsed is None and block:
                catalog["parser_warnings"].append({
                    "section": f"{pending['method']} /{pending['path']}",
                    "reason": f"could not parse {section} body as JSON",
                })
            elif parsed is not None:
                if section == "request":
                    pending["request_body_example"] = parsed
                    pending["request_body_schema"] = _infer_schema(parsed)
                elif section == "response":
                    pending["response_example"] = parsed
                    if pending["response_schema"] is None:
                        pending["response_schema"] = _infer_schema(parsed)
            i = next_i
            continue

        if stripped.startswith("+ Schema"):
            schema_indent = len(line) - len(line.lstrip(" "))
            block, next_i = _collect_indented_block(lines, i + 1, schema_indent + 4)
            parsed = _parse_json_block(block)
            if parsed is not None:
                section = pending.get("_section")
                if section == "request":
                    pending["request_body_schema"] = parsed
                elif section == "response":
                    pending["response_schema"] = parsed
            i = next_i
            continue

        # Parameter parsing inside `+ Parameters` block
        if pending.get("_section") == "parameters":
            indent = len(line) - len(line.lstrip(" "))
            if indent >= 4 and stripped.startswith("+ "):
                default_m = _DEFAULT_RE.match(line)
                if default_m and pending["query_params"]:
                    pending["query_params"][-1]["default"] = _parse_default(default_m.group(1))
                    i += 1
                    continue

                # Treat as a parameter declaration.
                m = _PARAM_RE.match(line)
                if m and m.group("name") and m.group("name") != "Default":
                    name = m.group("name")
                    modifiers = (m.group("modifiers") or "").strip()
                    description = (m.group("description") or "").strip()

                    required = False
                    raw_type: str | None = None
                    for token in (t.strip() for t in modifiers.split(",")):
                        if token.lower() == "required":
                            required = True
                        elif token.lower() == "optional":
                            required = False
                        elif token:
                            raw_type = token

                    default: Any = None
                    inline_default_m = _INLINE_DEFAULT_RE.search(description)
                    if inline_default_m:
                        raw_default = inline_default_m.group(1).strip()
                        if raw_default.lower() != "null":
                            default = _parse_default(raw_default)
                        description = _INLINE_DEFAULT_RE.sub("", description).rstrip()

                    pending["query_params"].append({
                        "name": name,
                        "type": _normalize_type(raw_type, default),
                        "required": required,
                        "default": default,
                        "description": description or None,
                    })
                    i += 1
                    continue

        i += 1

    flush()

    # Second pass: refine param types based on observed defaults.
    for endpoint in catalog["endpoints"]:
        for param in endpoint["query_params"]:
            if param["default"] is not None:
                param["type"] = _normalize_type(param["type"], param["default"])

    return catalog
