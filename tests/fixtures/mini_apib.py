"""A small API Blueprint sample for fast spec_parser unit tests.

Mirrors the structural conventions used in the real Cin7 Core API Blueprint:

  # Group <Group Name>
  ## <Resource Name> [/<resource path>]
  ### <Action Label> [<METHOD>]    (or [METHOD /full-path?foo={foo}])
  + Parameters
      + <Name> (optional|required, type) - description
          + Default: <value>
  + Request (application/json)
      + Body
              <JSON body content>
  + Response <code> (application/json)
      + Body
              <JSON body content>

Real Cin7 quirks captured:
- Path templates with `{?Page,Limit}` query-string interpolation.
- Bodies indented 12 spaces (4 spaces under the `+ Body` directive).
- Param defaults declared as a nested `+ Default: <value>` line.
"""

MINI_APIB = """FORMAT: 1A
HOST: https://example.test/v2/

# Demo API

## Intro

Some descriptive text.

# Group Product

Product CRUD operations.

## Product [/Product]

### Get a list of products [GET /Product?Page={Page}&Limit={Limit}&Sku={Sku}]
+ Parameters
    + Page (optional, number) ... Page number
        + Default: 1
    + Limit (optional, number) ... Page size
        + Default: 100
    + Sku (optional, string) ... Filter by SKU

+ Response 200 (application/json)
    + Body

            {
                "Total": 1,
                "Page": 1,
                "Products": [
                    {"ID": "abc", "SKU": "WIDGET-001", "Name": "Widget"}
                ]
            }

### Create a product [POST /Product]
+ Request (application/json)
    + Body

            {
                "SKU": "NEW-1",
                "Name": "New widget",
                "Category": "Misc"
            }

+ Response 201 (application/json)
    + Body

            {
                "ID": "new-id",
                "SKU": "NEW-1"
            }

# Group Sale

## Sale [/Sale]

### Get a single sale [GET /Sale?ID={ID}]
+ Parameters
    + ID (required, Guid) ... The sale ID

+ Response 200 (application/json)
    + Body

            {
                "ID": "sale-1",
                "Status": "DRAFT",
                "Lines": []
            }
"""
