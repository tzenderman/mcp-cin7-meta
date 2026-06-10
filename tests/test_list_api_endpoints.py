"""Tests for the list_api_endpoints MCP tool."""

import pytest

from cin7_meta.resources.endpoints import list_api_endpoints
from tests.conftest import MODULE_ENDPOINTS


@pytest.mark.asyncio
async def test_lists_matching_endpoints(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await list_api_endpoints("product")
    paths = [(r["method"], r["path"]) for r in result["results"]]
    assert ("GET", "Product") in paths
    assert ("POST", "Product") in paths


@pytest.mark.asyncio
async def test_methods_filter(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await list_api_endpoints("product", methods=["POST"])
    assert all(r["method"] == "POST" for r in result["results"])


@pytest.mark.asyncio
async def test_limit_truncates(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await list_api_endpoints("product", limit=1)
    assert len(result["results"]) == 1
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_empty_keyword_returns_error(patch_spec):
    with patch_spec(MODULE_ENDPOINTS):
        result = await list_api_endpoints("")
    assert "error" in result
