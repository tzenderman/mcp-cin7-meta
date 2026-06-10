"""A small normalized catalog for fast spec_loader / spec_search / resource tests.

Mirrors the schema written by `scripts/refresh_spec.py`: a dict with
`base_url`, `endpoints`, and `parser_warnings` keys.
"""

MINI_CATALOG = {
    "base_url": "https://example.test/v2/",
    "endpoints": [
        {
            "method": "GET",
            "path": "Product",
            "group": "Product",
            "summary": "List products",
            "description": "Paginated list of products.",
            "query_params": [
                {"name": "Page", "type": "integer", "required": False, "default": 1, "description": "Page number"},
                {"name": "Limit", "type": "integer", "required": False, "default": 100, "description": "Page size"},
                {"name": "Sku", "type": "string", "required": False, "default": None, "description": "Filter by SKU"},
            ],
            "request_body_schema": None,
            "request_body_example": None,
            "response_schema": {"type": "object", "properties": {"Products": {"type": "array"}, "Total": {"type": "integer"}}},
            "response_example": {"Total": 1, "Products": [{"ID": "p1", "SKU": "X"}]},
        },
        {
            "method": "POST",
            "path": "Product",
            "group": "Product",
            "summary": "Create a product",
            "description": "",
            "query_params": [],
            "request_body_schema": {
                "type": "object",
                "properties": {"SKU": {"type": "string"}, "Name": {"type": "string"}, "Category": {"type": "string"}},
                "required": ["SKU", "Name"],
            },
            "request_body_example": {"SKU": "NEW-1", "Name": "Widget", "Category": "Misc"},
            "response_schema": {"type": "object"},
            "response_example": {"ID": "new-id"},
        },
        {
            "method": "GET",
            "path": "Sale",
            "group": "Sale",
            "summary": "Get a single sale",
            "description": "",
            "query_params": [
                {"name": "ID", "type": "string", "required": True, "default": None, "description": "The sale ID"},
            ],
            "request_body_schema": None,
            "request_body_example": None,
            "response_schema": {"type": "object"},
            "response_example": {"ID": "sale-1", "Status": "DRAFT"},
        },
        {
            "method": "GET",
            "path": "saleList",
            "group": "Sale",
            "summary": "List sales",
            "description": "",
            "query_params": [
                {"name": "Page", "type": "integer", "required": False, "default": 1, "description": None},
                {"name": "Search", "type": "string", "required": False, "default": None, "description": "Full-text search"},
            ],
            "request_body_schema": None,
            "request_body_example": None,
            "response_schema": None,
            "response_example": None,
        },
    ],
    "parser_warnings": [],
}
