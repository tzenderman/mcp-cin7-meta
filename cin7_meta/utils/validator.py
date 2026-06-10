"""Validate an `invoke_api_endpoint` request before it leaves the process.

Mirrors `shopify_meta/utils/validator.py` in shape: pure-function entry,
no exceptions cross the boundary, structured `[{"message", "field"}]` errors.

For Cin7 specifically:
- Query params: strict on unknown names, required-ness, and primitive types.
- Body: strict on required fields *declared* in the request body schema,
  permissive on extras (Cin7 accepts undocumented body fields).
"""

from __future__ import annotations

from typing import Any

from .spec_loader import EndpointDef, ParamDef

_BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _err(message: str, field: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"message": message}
    if field is not None:
        out["field"] = field
    return out


def _coerce_int(value: Any) -> tuple[bool, Any]:
    if isinstance(value, bool):
        return False, None
    if isinstance(value, int):
        return True, value
    if isinstance(value, str):
        try:
            return True, int(value)
        except ValueError:
            return False, None
    return False, None


def _coerce_number(value: Any) -> tuple[bool, Any]:
    if isinstance(value, bool):
        return False, None
    if isinstance(value, (int, float)):
        return True, value
    if isinstance(value, str):
        try:
            return True, float(value)
        except ValueError:
            return False, None
    return False, None


def _coerce_bool(value: Any) -> tuple[bool, Any]:
    if isinstance(value, bool):
        return True, value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower == "true":
            return True, True
        if lower == "false":
            return True, False
    return False, None


def _validate_param(param: ParamDef, value: Any) -> dict | None:
    if param.type == "integer":
        ok, _ = _coerce_int(value)
        if not ok:
            return _err(
                f"Query param {param.name!r} expects integer, got {value!r}",
                field=param.name,
            )
    elif param.type == "number":
        ok, _ = _coerce_number(value)
        if not ok:
            return _err(
                f"Query param {param.name!r} expects number, got {value!r}",
                field=param.name,
            )
    elif param.type == "boolean":
        ok, _ = _coerce_bool(value)
        if not ok:
            return _err(
                f"Query param {param.name!r} expects boolean, got {value!r}",
                field=param.name,
            )
    elif param.type == "string":
        if not isinstance(value, str) and not isinstance(value, (int, float, bool)):
            return _err(
                f"Query param {param.name!r} expects string, got {type(value).__name__}",
                field=param.name,
            )
    return None


def validate_invocation(
    endpoint: EndpointDef,
    query_params: dict[str, Any] | None,
    body: dict[str, Any] | None,
) -> list[dict]:
    """Validate a tool-layer invocation against an endpoint's schema.

    Returns a list of error dicts; an empty list means the call is valid.

    Validation rules:
      - Query: reject unknown names. Check `required`. Coerce/type-check.
      - Body: if the endpoint has a body schema declaring `required` fields,
        each must be present. Extra fields are permitted (Cin7 accepts them).
        For POST/PUT/PATCH/DELETE endpoints whose schema declares required
        fields, a `None` body is rejected.
    """
    errors: list[dict] = []
    qp = query_params or {}

    declared = {p.name: p for p in endpoint.query_params}

    for name in qp:
        if name not in declared:
            errors.append(_err(
                f"Unknown query param {name!r} for {endpoint.method} /{endpoint.path}. "
                f"Allowed: {sorted(declared)}",
                field=name,
            ))

    for param in endpoint.query_params:
        if param.required and param.name not in qp:
            errors.append(_err(
                f"Required query param {param.name!r} is missing.",
                field=param.name,
            ))

    for name, value in qp.items():
        if name in declared:
            param_err = _validate_param(declared[name], value)
            if param_err:
                errors.append(param_err)

    # Body validation: only when the endpoint declares a body schema.
    schema = endpoint.request_body_schema
    if endpoint.method in _BODY_METHODS and schema:
        required_fields = list(schema.get("required") or [])

        if required_fields and not body:
            errors.append(_err(
                f"{endpoint.method} /{endpoint.path} requires a request body with fields: "
                f"{required_fields}",
                field=None,
            ))
        elif body and required_fields:
            for field in required_fields:
                if field not in body:
                    errors.append(_err(
                        f"Required body field {field!r} is missing.",
                        field=field,
                    ))

    return errors
