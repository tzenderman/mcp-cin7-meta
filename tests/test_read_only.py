"""Tests for opt-in read-only mode (`CIN7_READ_ONLY`).

Two independent layers are covered:

* the `invoke_api_endpoint` tool, which must refuse before any network call and
  return a structured error the model can read;
* `Cin7Client.invoke()`, the chokepoint every request passes through, which
  must raise before a request is built even if a caller skips the tool layer.
"""

import pytest

from cin7_meta.resources.invoke import invoke_api_endpoint
from cin7_meta.server import create_mcp_server
from cin7_meta.utils.cin7_client import Cin7Client
from cin7_meta.utils.errors import Cin7ReadOnlyError
from cin7_meta.utils.read_only import (
    READ_ONLY_ENV_VAR,
    is_read_only,
    method_is_allowed,
)
from tests.conftest import MODULE_INVOKE

WRITE_METHODS = ["POST", "PUT", "PATCH", "DELETE"]


@pytest.fixture
def read_only(monkeypatch):
    """Turn read-only mode on for the duration of a test."""
    monkeypatch.setenv(READ_ONLY_ENV_VAR, "1")


@pytest.fixture
def read_write(monkeypatch):
    """Explicitly ensure read-only mode is off (the default)."""
    monkeypatch.delenv(READ_ONLY_ENV_VAR, raising=False)


# --------------------------------------------------------------------------
# is_read_only / method_is_allowed
# --------------------------------------------------------------------------


def test_default_is_read_write(read_write):
    assert is_read_only() is False
    for method in WRITE_METHODS:
        assert method_is_allowed(method) is True


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " True "])
def test_truthy_values_enable_read_only(monkeypatch, value):
    monkeypatch.setenv(READ_ONLY_ENV_VAR, value)
    assert is_read_only() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_non_truthy_values_leave_it_off(monkeypatch, value):
    monkeypatch.setenv(READ_ONLY_ENV_VAR, value)
    assert is_read_only() is False


def test_get_allowed_and_writes_blocked_when_read_only(read_only):
    assert method_is_allowed("GET") is True
    assert method_is_allowed("get") is True
    for method in WRITE_METHODS:
        assert method_is_allowed(method) is False
        assert method_is_allowed(method.lower()) is False


# --------------------------------------------------------------------------
# Layer 1 — the invoke_api_endpoint tool
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method", WRITE_METHODS)
async def test_write_refused_before_network(read_only, patch_spec, mock_cin7, method):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(200, {}, {})
    ) as client:
        result = await invoke_api_endpoint(method=method, path="Product", body={})

    assert result["status"] is None
    assert result["data"] is None
    assert any("read-only" in e["message"].lower() for e in result["errors"])
    client.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_still_works_when_read_only(read_only, patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE,
        return_value=(200, {"Products": []}, {"X-RateLimit-Remaining": "58"}),
    ) as client:
        result = await invoke_api_endpoint(
            method="GET", path="Product", query_params={"Page": 1}
        )

    assert result["status"] == 200
    assert result["data"] == {"Products": []}
    client.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_allowed_when_mode_is_off(read_write, patch_spec, mock_cin7):
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(200, {"ID": "abc"}, {})
    ) as client:
        result = await invoke_api_endpoint(
            method="POST", path="Product", body={"Name": "Test", "SKU": "T-1"}
        )

    assert result["status"] == 200
    client.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_only_refusal_precedes_unknown_endpoint(
    read_only, patch_spec, mock_cin7
):
    """A write to a bogus path reports read-only, not 'endpoint not found'."""
    with patch_spec(MODULE_INVOKE), mock_cin7(
        MODULE_INVOKE, return_value=(200, {}, {})
    ) as client:
        result = await invoke_api_endpoint(method="POST", path="Producttypo", body={})

    assert any("read-only" in e["message"].lower() for e in result["errors"])
    assert not any("not found" in e["message"].lower() for e in result["errors"])
    client.invoke.assert_not_awaited()


# --------------------------------------------------------------------------
# Layer 2 — Cin7Client.invoke, the chokepoint
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method", WRITE_METHODS)
async def test_client_raises_on_write_when_read_only(read_only, method):
    client = Cin7Client(
        base_url="https://example.invalid/", account_id="acct", application_key="key"
    )
    # No HTTP mocking: if the guard failed to fire, this would attempt a real
    # request to an unresolvable host and fail with a different error.
    with pytest.raises(Cin7ReadOnlyError) as exc:
        await client.invoke(method, "Product", body={})

    assert "read-only" in str(exc.value).lower()


# --------------------------------------------------------------------------
# Server instructions
# --------------------------------------------------------------------------


def test_server_instructions_announce_read_only(read_only):
    mcp = create_mcp_server()
    assert "READ-ONLY MODE" in mcp.instructions


def test_server_instructions_silent_when_read_write(read_write):
    mcp = create_mcp_server()
    assert "READ-ONLY MODE" not in mcp.instructions
