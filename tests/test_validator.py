"""Tests for the request validator (query params + body)."""

import pytest

from cin7_meta.utils.spec_loader import load_spec_from_dict
from cin7_meta.utils.validator import validate_invocation
from tests.fixtures.mini_spec import MINI_CATALOG


@pytest.fixture
def spec():
    return load_spec_from_dict(MINI_CATALOG)


def test_valid_get_returns_no_errors(spec):
    endpoint = spec.get_endpoint("GET", "Product")
    errors = validate_invocation(endpoint, query_params={"Page": 1, "Limit": 50}, body=None)
    assert errors == []


def test_unknown_query_param_rejected(spec):
    endpoint = spec.get_endpoint("GET", "Product")
    errors = validate_invocation(endpoint, query_params={"BadKey": "x"}, body=None)
    assert errors
    assert any("BadKey" in e["message"] for e in errors)


def test_missing_required_query_param_rejected(spec):
    endpoint = spec.get_endpoint("GET", "Sale")
    # `ID` is required; passing nothing should error.
    errors = validate_invocation(endpoint, query_params={}, body=None)
    assert errors
    assert any("ID" in e["message"] and "required" in e["message"].lower() for e in errors)


def test_required_param_present_passes(spec):
    endpoint = spec.get_endpoint("GET", "Sale")
    errors = validate_invocation(endpoint, query_params={"ID": "abc-123"}, body=None)
    assert errors == []


def test_wrong_type_int_rejected(spec):
    """Pass a non-integer where an integer is expected."""
    endpoint = spec.get_endpoint("GET", "Product")
    errors = validate_invocation(endpoint, query_params={"Page": "not-an-int"}, body=None)
    assert errors
    assert any("Page" in e["message"] and "integer" in e["message"].lower() for e in errors)


def test_int_as_string_coerces(spec):
    """A string like '1' for an integer param is acceptable (Cin7 sends query params as strings anyway)."""
    endpoint = spec.get_endpoint("GET", "Product")
    errors = validate_invocation(endpoint, query_params={"Page": "1"}, body=None)
    assert errors == []


def test_int_param_accepts_native_int(spec):
    endpoint = spec.get_endpoint("GET", "Product")
    errors = validate_invocation(endpoint, query_params={"Page": 5}, body=None)
    assert errors == []


def test_bool_param_accepts_true_false_strings():
    """A boolean param accepts 'true'/'false' strings and native booleans."""
    catalog = {
        "base_url": "x/",
        "endpoints": [
            {
                "method": "GET",
                "path": "Foo",
                "group": "Foo",
                "summary": "",
                "description": "",
                "query_params": [
                    {"name": "Flag", "type": "boolean", "required": False, "default": None, "description": None}
                ],
                "request_body_schema": None,
                "request_body_example": None,
                "response_schema": None,
                "response_example": None,
            }
        ],
        "parser_warnings": [],
    }
    spec = load_spec_from_dict(catalog)
    endpoint = spec.get_endpoint("GET", "Foo")
    assert validate_invocation(endpoint, query_params={"Flag": True}, body=None) == []
    assert validate_invocation(endpoint, query_params={"Flag": "true"}, body=None) == []
    assert validate_invocation(endpoint, query_params={"Flag": "False"}, body=None) == []
    errors = validate_invocation(endpoint, query_params={"Flag": "maybe"}, body=None)
    assert errors and any("Flag" in e["message"] for e in errors)


def test_post_with_required_body_fields_present(spec):
    """POST /Product requires SKU and Name; supplying them passes."""
    endpoint = spec.get_endpoint("POST", "Product")
    errors = validate_invocation(
        endpoint, query_params=None, body={"SKU": "X", "Name": "Widget"}
    )
    assert errors == []


def test_post_missing_required_body_field(spec):
    endpoint = spec.get_endpoint("POST", "Product")
    errors = validate_invocation(endpoint, query_params=None, body={"SKU": "X"})
    assert errors
    assert any("Name" in e["message"] and "required" in e["message"].lower() for e in errors)


def test_post_body_with_extra_fields_allowed(spec):
    """Cin7 accepts body fields beyond what the schema documents — extras are permitted."""
    endpoint = spec.get_endpoint("POST", "Product")
    errors = validate_invocation(
        endpoint,
        query_params=None,
        body={"SKU": "X", "Name": "Widget", "RandomExtra": "ok", "AlsoExtra": 1},
    )
    assert errors == []


def test_post_with_missing_body_when_required(spec):
    endpoint = spec.get_endpoint("POST", "Product")
    errors = validate_invocation(endpoint, query_params=None, body=None)
    assert errors
    assert any("body" in e["message"].lower() for e in errors)


def test_get_endpoint_ignores_body(spec):
    """A GET endpoint has no request body schema — body=None is fine; passing body is also fine (ignored)."""
    endpoint = spec.get_endpoint("GET", "Product")
    assert validate_invocation(endpoint, query_params=None, body=None) == []
    # Even if body is passed, GET endpoints don't validate it
    assert validate_invocation(endpoint, query_params=None, body={"X": "Y"}) == []


def test_error_dict_has_message_and_field(spec):
    endpoint = spec.get_endpoint("GET", "Product")
    errors = validate_invocation(endpoint, query_params={"BadKey": "x"}, body=None)
    assert errors
    err = errors[0]
    assert "message" in err
    assert err.get("field") == "BadKey"
