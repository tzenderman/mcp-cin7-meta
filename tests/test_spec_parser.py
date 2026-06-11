"""Tests for the API Blueprint -> normalized JSON catalog parser."""

import pytest

from cin7_meta.utils.spec_parser import parse_apib
from tests.fixtures.mini_apib import MINI_APIB


@pytest.fixture
def catalog():
    return parse_apib(MINI_APIB)


def test_returns_dict_with_endpoints_and_metadata(catalog):
    assert isinstance(catalog, dict)
    assert "endpoints" in catalog
    assert "parser_warnings" in catalog
    assert "base_url" in catalog


def test_extracts_host_as_base_url(catalog):
    assert catalog["base_url"] == "https://example.test/v2/"


def test_finds_all_three_endpoints(catalog):
    methods_paths = {(e["method"], e["path"]) for e in catalog["endpoints"]}
    assert methods_paths == {
        ("GET", "Product"),
        ("POST", "Product"),
        ("GET", "Sale"),
    }


def _find(catalog, method, path):
    for e in catalog["endpoints"]:
        if e["method"] == method and e["path"] == path:
            return e
    raise AssertionError(f"endpoint {method} {path} not found in catalog")


def test_group_captured(catalog):
    get_product = _find(catalog, "GET", "Product")
    assert get_product["group"] == "Product"
    get_sale = _find(catalog, "GET", "Sale")
    assert get_sale["group"] == "Sale"


def test_get_product_has_three_query_params(catalog):
    e = _find(catalog, "GET", "Product")
    names = [p["name"] for p in e["query_params"]]
    assert names == ["Page", "Limit", "Sku"]


def test_query_param_optional_required(catalog):
    e = _find(catalog, "GET", "Product")
    page = next(p for p in e["query_params"] if p["name"] == "Page")
    sku = next(p for p in e["query_params"] if p["name"] == "Sku")
    assert page["required"] is False
    assert sku["required"] is False

    sale = _find(catalog, "GET", "Sale")
    id_param = next(p for p in sale["query_params"] if p["name"] == "ID")
    assert id_param["required"] is True


def test_query_param_type_normalized(catalog):
    """`number` -> integer (because default is an int), `string` stays string, `Guid` -> string."""
    get_product = _find(catalog, "GET", "Product")
    page = next(p for p in get_product["query_params"] if p["name"] == "Page")
    assert page["type"] == "integer"
    sku = next(p for p in get_product["query_params"] if p["name"] == "Sku")
    assert sku["type"] == "string"

    sale = _find(catalog, "GET", "Sale")
    id_param = next(p for p in sale["query_params"] if p["name"] == "ID")
    assert id_param["type"] == "string"


def test_query_param_default_parsed(catalog):
    e = _find(catalog, "GET", "Product")
    page = next(p for p in e["query_params"] if p["name"] == "Page")
    limit = next(p for p in e["query_params"] if p["name"] == "Limit")
    sku = next(p for p in e["query_params"] if p["name"] == "Sku")
    assert page["default"] == 1
    assert limit["default"] == 100
    assert sku["default"] is None


def test_query_param_description_parsed(catalog):
    e = _find(catalog, "GET", "Product")
    page = next(p for p in e["query_params"] if p["name"] == "Page")
    assert "Page number" in (page["description"] or "")


def test_response_body_example_parsed(catalog):
    e = _find(catalog, "GET", "Product")
    assert e["response_example"]["Total"] == 1
    assert e["response_example"]["Products"][0]["SKU"] == "WIDGET-001"


def test_response_schema_inferred_when_only_body(catalog):
    """No explicit `+ Schema` in fixture, so schema is inferred from body shape."""
    e = _find(catalog, "GET", "Product")
    schema = e["response_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "Products" in schema["properties"]


def test_post_has_request_body_example(catalog):
    e = _find(catalog, "POST", "Product")
    assert e["request_body_example"]["SKU"] == "NEW-1"
    assert e["request_body_example"]["Name"] == "New widget"


def test_post_has_request_body_schema(catalog):
    e = _find(catalog, "POST", "Product")
    schema = e["request_body_schema"]
    assert schema is not None
    assert schema["type"] == "object"
    assert "SKU" in schema["properties"]


def test_get_endpoints_have_no_request_body(catalog):
    e = _find(catalog, "GET", "Product")
    assert e["request_body_example"] is None
    assert e["request_body_schema"] is None


def test_path_template_stripped():
    """Resource path `/Product{?Page,Limit}` is normalized to `Product`."""
    src = """FORMAT: 1A
HOST: https://x/

# Group Foo
## Foo [/Foo{?Page,Limit}]
### List [GET]
+ Response 200 (application/json)
    + Body

            {"ok": true}
"""
    cat = parse_apib(src)
    assert any(e["method"] == "GET" and e["path"] == "Foo" for e in cat["endpoints"])


def test_skips_intro_group_with_no_endpoints():
    src = """FORMAT: 1A
HOST: https://x/

# Cin7 Core
## Introduction

Some text.

# Group Foo
## Foo [/Foo]
### List [GET]
+ Response 200 (application/json)
    + Body

            {"ok": true}
"""
    cat = parse_apib(src)
    assert {(e["method"], e["path"]) for e in cat["endpoints"]} == {("GET", "Foo")}


def test_summary_taken_from_action_label(catalog):
    e = _find(catalog, "GET", "Product")
    assert "list of products" in e["summary"].lower()


def test_method_only_action_header_falls_back_to_resource_path():
    """When the action header is just `### Get [GET]` (no inline path), use the parent resource path."""
    src = """FORMAT: 1A
HOST: https://x/

# Group Foo
## Foo [/Foo]
### Fetch all [GET]
+ Response 200 (application/json)
    + Body

            {"ok": true}
"""
    cat = parse_apib(src)
    e = next(e for e in cat["endpoints"] if e["method"] == "GET")
    assert e["path"] == "Foo"


def test_trailing_comma_in_request_body_is_tolerated():
    """The Cin7 blueprint's JSON examples have trailing commas (invalid JSON).

    The parser must still capture the body rather than dropping it with a warning.
    """
    src = """FORMAT: 1A
HOST: https://x/

# Group Supplier
## Supplier [/supplier]
### POST [POST]
+ Request (application/json)
    + Body

            {
                "Name": "Acme",
                "Currency": "USD",
            }

+ Response 200 (application/json)
    + Body

            {"ok": true}
"""
    cat = parse_apib(src)
    e = next(e for e in cat["endpoints"] if e["method"] == "POST")
    assert e["request_body_example"] == {"Name": "Acme", "Currency": "USD"}
    assert e["request_body_schema"] is not None
    assert "Name" in e["request_body_schema"]["properties"]
    assert not any("request body" in w["reason"].lower() for w in cat["parser_warnings"])


def test_trailing_comma_in_nested_response_body_is_tolerated():
    """Trailing commas appear inside nested arrays/objects too."""
    src = """FORMAT: 1A
HOST: https://x/

# Group Supplier
## Supplier [/supplier]
### GET [GET /supplier]
+ Response 200 (application/json)
    + Body

            {
                "Total": 1,
                "SupplierList": [
                    {"ID": "a", "Name": "Acme",},
                ],
            }
"""
    cat = parse_apib(src)
    e = next(e for e in cat["endpoints"] if e["method"] == "GET")
    assert e["response_example"]["SupplierList"][0]["Name"] == "Acme"
    assert "SupplierList" in e["response_schema"]["properties"]


def test_bare_method_labels_get_descriptive_summaries():
    """When the blueprint's action label is just the HTTP method (`### POST [POST]`),
    synthesize a verb+resource summary so the model can tell readers from writers.
    A GET with the Cin7 list envelope (`*List` array) reads as "List", not "Get".
    """
    src = """FORMAT: 1A
HOST: https://x/

# Group Supplier
## Supplier [/supplier]
### GET [GET /supplier?Page={Page}]
+ Response 200 (application/json)
    + Body

            {"Total": 1, "SupplierList": [{"ID": "a"}]}

### POST [POST]
+ Request (application/json)
    + Body

            {"Name": "Acme"}

+ Response 200 (application/json)
    + Body

            {"ID": "a"}

### PUT [PUT]
+ Request (application/json)
    + Body

            {"ID": "a", "Name": "Acme2"}

+ Response 200 (application/json)
    + Body

            {"ID": "a"}
"""
    cat = parse_apib(src)
    get = next(e for e in cat["endpoints"] if e["method"] == "GET")
    post = next(e for e in cat["endpoints"] if e["method"] == "POST")
    put = next(e for e in cat["endpoints"] if e["method"] == "PUT")
    assert get["summary"] == "List Supplier"
    assert post["summary"] == "Create Supplier"
    assert put["summary"] == "Update Supplier"


def test_bare_method_single_get_and_delete_summaries():
    """A GET without a list envelope reads as "Get"; DELETE reads as "Delete"."""
    src = """FORMAT: 1A
HOST: https://x/

# Group Sale
## Sale [/Sale]
### GET [GET /Sale?ID={ID}]
+ Response 200 (application/json)
    + Body

            {"ID": "s1", "Status": "DRAFT", "Lines": []}

### DELETE [DELETE /Sale?ID={ID}]
+ Response 200 (application/json)
    + Body

            {"ok": true}
"""
    cat = parse_apib(src)
    get = next(e for e in cat["endpoints"] if e["method"] == "GET")
    delete = next(e for e in cat["endpoints"] if e["method"] == "DELETE")
    assert get["summary"] == "Get Sale"
    assert delete["summary"] == "Delete Sale"


def test_descriptive_action_labels_are_not_overwritten(catalog):
    """A real, human-written action label must survive summary synthesis."""
    get = _find(catalog, "GET", "Product")
    post = _find(catalog, "POST", "Product")
    assert "list of products" in get["summary"].lower()
    assert "create a product" in post["summary"].lower()


def test_unparseable_section_recorded_as_warning_not_exception():
    """An action with malformed parameter syntax shouldn't break parsing; the endpoint still ships."""
    src = """FORMAT: 1A
HOST: https://x/

# Group Foo
## Foo [/Foo]
### Bad [GET /Foo]
+ Parameters
    this isn't a parameter

+ Response 200 (application/json)
    + Body

            not-json-content
"""
    cat = parse_apib(src)
    # The endpoint should still be present.
    assert any(e["method"] == "GET" and e["path"] == "Foo" for e in cat["endpoints"])
    # The unparseable body should produce a warning.
    assert any("response" in w.get("reason", "").lower() or "body" in w.get("reason", "").lower()
               for w in cat["parser_warnings"])
