"""Tests for the invoke_api_endpoint MCP tool."""

import pytest

from cin7_meta.resources.invoke import invoke_api_endpoint
from cin7_meta.utils.errors import (
    Cin7APIError,
    Cin7AuthError,
    Cin7NotFoundError,
    Cin7RateLimitError,
)
from tests.conftest import MODULE_INVOKE


@pytest.mark.asyncio
async def test_success_returns_status_data_rate_limit(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE,
        return_value=(200, {"Products": []}, {"X-RateLimit-Remaining": "58"}),
    ) as client:
        result = await invoke_api_endpoint(
            method="GET", path="Product", query_params={"Page": 1}
        )

    assert result["status"] == 200
    assert result["data"] == {"Products": []}
    assert result["rate_limit_remaining"] == "58"
    client.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_endpoint_rejected_before_network(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(200, {}, {})
    ) as client:
        result = await invoke_api_endpoint(
            method="GET", path="Producttypo", query_params={}
        )

    assert result["status"] is None
    assert result["data"] is None
    assert result["errors"]
    assert any("not found" in e["message"].lower() for e in result["errors"])
    client.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_query_param_rejected_before_network(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(200, {}, {})
    ) as client:
        result = await invoke_api_endpoint(
            method="GET", path="Product", query_params={"BadKey": "x"}
        )

    assert result["status"] is None
    assert any("BadKey" in e["message"] for e in result["errors"])
    client.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_type_rejected_before_network(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(200, {}, {})
    ) as client:
        result = await invoke_api_endpoint(
            method="GET", path="Product", query_params={"Page": "not-an-int"}
        )

    assert any("integer" in e["message"].lower() for e in result["errors"])
    client.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_required_body_field_rejected_before_network(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(201, {"ID": "x"}, {})
    ) as client:
        result = await invoke_api_endpoint(
            method="POST", path="Product", body={"SKU": "X"}  # missing Name
        )

    assert any("Name" in e["message"] for e in result["errors"])
    client.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_with_required_body_succeeds(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(201, {"ID": "p1"}, {"X-RateLimit-Remaining": "59"})
    ) as client:
        result = await invoke_api_endpoint(
            method="POST", path="Product", body={"SKU": "X", "Name": "Widget"}
        )

    assert result["status"] == 201
    assert result["data"]["ID"] == "p1"
    client.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_cin7_400_returned_as_errors(patch_spec, mock_cin7):
    """A 4xx response from Cin7 is returned to the model as `errors`."""
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE,
        return_value=(400, [{"Exception": "Bad SKU"}], {"X-RateLimit-Remaining": "55"}),
    ):
        result = await invoke_api_endpoint(
            method="GET", path="Product", query_params={"Sku": "bad"}
        )

    assert result["status"] == 400
    assert result["data"] == [{"Exception": "Bad SKU"}]
    assert result["errors"]


@pytest.mark.asyncio
async def test_auth_error_propagates_to_tool_error(patch_spec, mock_cin7):
    """Auth errors are not the model's fault — let them bubble up."""
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, side_effect=Cin7AuthError("bad creds")
    ):
        with pytest.raises(Cin7AuthError):
            await invoke_api_endpoint(method="GET", path="Product", query_params={"Page": 1})


@pytest.mark.asyncio
async def test_rate_limit_error_propagates(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, side_effect=Cin7RateLimitError("rate limit")
    ):
        with pytest.raises(Cin7RateLimitError):
            await invoke_api_endpoint(method="GET", path="Product")


@pytest.mark.asyncio
async def test_passes_query_params_and_body_through(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(201, {"ID": "p1"}, {})
    ) as client:
        await invoke_api_endpoint(
            method="POST",
            path="Product",
            body={"SKU": "X", "Name": "Widget"},
        )

    call = client.invoke.await_args
    # Tool delegates to client.invoke(method, path, query_params=..., body=...)
    kwargs = call.kwargs
    assert call.args[0] == "POST"
    assert call.args[1] == "Product"
    assert kwargs.get("body") == {"SKU": "X", "Name": "Widget"}


@pytest.mark.asyncio
async def test_path_normalization_works(patch_spec, mock_cin7):
    """Both `/Product` and `Product` resolve to the same endpoint."""
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(200, {}, {})
    ) as client:
        result = await invoke_api_endpoint(method="GET", path="/Product")
    assert result["status"] == 200
    client.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_rate_limit_header_returns_none(patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(200, {}, {})
    ):
        result = await invoke_api_endpoint(method="GET", path="Product")
    assert result.get("rate_limit_remaining") is None
