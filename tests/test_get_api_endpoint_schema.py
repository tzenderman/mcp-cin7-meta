"""Tests for the get_api_endpoint_schema MCP tool."""

import pytest

from cin7_meta.resources.endpoints import get_api_endpoint_schema
from tests.conftest import MODULE_ENDPOINTS


@pytest.mark.asyncio
async def test_returns_full_schema(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await get_api_endpoint_schema(method="GET", path="Product")
    assert result["method"] == "GET"
    assert result["path"] == "Product"
    assert result["group"] == "Product"
    assert result["summary"] == "List products"
    assert len(result["query_params"]) == 3


@pytest.mark.asyncio
async def test_path_normalization(patch_spec):
    """Both `/Product` and `Product` resolve to the same endpoint."""
    with patch_spec(MODULE_ENDPOINTS):
        a = await get_api_endpoint_schema(method="GET", path="/Product")
        b = await get_api_endpoint_schema(method="GET", path="Product")
    assert a["path"] == b["path"]


@pytest.mark.asyncio
async def test_method_case_insensitive(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await get_api_endpoint_schema(method="get", path="Product")
    assert result["method"] == "GET"


@pytest.mark.asyncio
async def test_unknown_endpoint_returns_error_with_suggestion(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await get_api_endpoint_schema(method="GET", path="Producttypo")
    assert "error" in result
    assert "did_you_mean" in result


@pytest.mark.asyncio
async def test_get_endpoint_has_no_request_body(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await get_api_endpoint_schema(method="GET", path="Product")
    assert result["request_body_schema"] is None
    assert result["request_body_example"] is None


@pytest.mark.asyncio
async def test_post_endpoint_includes_request_body(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await get_api_endpoint_schema(method="POST", path="Product")
    assert result["request_body_schema"] is not None
    assert "SKU" in result["request_body_schema"]["properties"]


@pytest.mark.asyncio
async def test_response_example_included(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await get_api_endpoint_schema(method="GET", path="Product")
    assert result["response_example"]["Total"] == 1
