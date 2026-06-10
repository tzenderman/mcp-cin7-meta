"""Tests for the Cin7 client with retry logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cin7_meta.utils.cin7_client import Cin7Client
from cin7_meta.utils.errors import (
    Cin7APIError,
    Cin7AuthError,
    Cin7NotFoundError,
    Cin7RateLimitError,
)


def _make_response(status_code, json_data=None, text="", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no body")
    return resp


def _make_mock_client(method_name: str, *, return_value=None, side_effect=None):
    """Create a mock httpx.AsyncClient async-context-manager that returns/raises from `method_name`."""
    inner = AsyncMock()
    if side_effect is not None:
        getattr(inner, method_name).side_effect = side_effect
    else:
        getattr(inner, method_name).return_value = return_value
    inner.__aenter__ = AsyncMock(return_value=inner)
    inner.__aexit__ = AsyncMock(return_value=False)
    return inner


@pytest.fixture
def client():
    c = Cin7Client(
        base_url="https://example.com/ExternalApi/v2/",
        account_id="acct-123",
        application_key="key-abc",
    )
    c.retry_delays = [0, 0, 0]
    return c


class TestFromEnv:
    def test_reads_required_env(self, monkeypatch):
        monkeypatch.setenv("CIN7_ACCOUNT_ID", "acct-1")
        monkeypatch.setenv("CIN7_API_KEY", "k1")
        monkeypatch.delenv("CIN7_BASE_URL", raising=False)
        c = Cin7Client.from_env()
        assert c.account_id == "acct-1"
        assert c.application_key == "k1"
        # default base url
        assert c.base_url == "https://inventory.dearsystems.com/ExternalApi/v2/"

    def test_base_url_override(self, monkeypatch):
        monkeypatch.setenv("CIN7_ACCOUNT_ID", "a")
        monkeypatch.setenv("CIN7_API_KEY", "k")
        monkeypatch.setenv("CIN7_BASE_URL", "https://other.example/api/v2")
        c = Cin7Client.from_env()
        # trailing slash auto-appended
        assert c.base_url == "https://other.example/api/v2/"

    def test_missing_creds_raises_auth_error(self, monkeypatch):
        monkeypatch.delenv("CIN7_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("CIN7_API_KEY", raising=False)
        with pytest.raises(Cin7AuthError):
            Cin7Client.from_env()


@pytest.mark.asyncio
class TestInvoke:
    async def test_get_success_returns_status_data_headers(self, client):
        response = _make_response(
            200,
            {"Products": [{"ID": "p1"}], "Total": 1},
            headers={"X-RateLimit-Remaining": "59"},
        )
        mock_client = _make_mock_client("get", return_value=response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            status, body, headers = await client.invoke("GET", "Product", query_params={"Page": 1})

        assert status == 200
        assert body == {"Products": [{"ID": "p1"}], "Total": 1}
        assert headers["X-RateLimit-Remaining"] == "59"

    async def test_get_passes_query_params(self, client):
        response = _make_response(200, {"Products": []})
        mock_client = _make_mock_client("get", return_value=response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await client.invoke("GET", "Product", query_params={"Page": 2, "Limit": 50})

        mock_client.get.assert_awaited_once()
        call = mock_client.get.call_args
        assert call.args[0] == "Product"
        assert call.kwargs.get("params") == {"Page": 2, "Limit": 50}

    async def test_post_passes_body(self, client):
        response = _make_response(201, {"ID": "new-id"})
        mock_client = _make_mock_client("post", return_value=response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await client.invoke("POST", "Product", body={"SKU": "X"})

        call = mock_client.post.call_args
        assert call.args[0] == "Product"
        assert call.kwargs.get("json") == {"SKU": "X"}

    async def test_method_case_insensitive(self, client):
        response = _make_response(200, {})
        mock_client = _make_mock_client("get", return_value=response)
        with patch("httpx.AsyncClient", return_value=mock_client):
            status, _, _ = await client.invoke("get", "Product")
        assert status == 200

    async def test_path_leading_slash_stripped(self, client):
        response = _make_response(200, {})
        mock_client = _make_mock_client("get", return_value=response)
        with patch("httpx.AsyncClient", return_value=mock_client):
            await client.invoke("GET", "/Product")
        call = mock_client.get.call_args
        assert call.args[0] == "Product"

    async def test_401_raises_auth_error_no_retry(self, client):
        response = _make_response(401, text="unauthorized")
        mock_client = _make_mock_client("get", return_value=response)
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Cin7AuthError):
                await client.invoke("GET", "Product")
        assert mock_client.get.await_count == 1

    async def test_404_raises_not_found_no_retry(self, client):
        response = _make_response(404, text="not found")
        mock_client = _make_mock_client("get", return_value=response)
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Cin7NotFoundError):
                await client.invoke("GET", "Doesnotexist")
        assert mock_client.get.await_count == 1

    async def test_429_retries_then_raises(self, client):
        resp_429 = _make_response(429, text="rate limit")
        mock_client = _make_mock_client(
            "get", side_effect=[resp_429, resp_429, resp_429]
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Cin7RateLimitError):
                await client.invoke("GET", "Product")
        assert mock_client.get.await_count == 3

    async def test_429_retry_then_succeeds(self, client):
        resp_429 = _make_response(429, text="rate limit")
        resp_200 = _make_response(200, {"Products": []})
        mock_client = _make_mock_client("get", side_effect=[resp_429, resp_200])
        with patch("httpx.AsyncClient", return_value=mock_client):
            status, body, _ = await client.invoke("GET", "Product")
        assert status == 200
        assert mock_client.get.await_count == 2

    async def test_5xx_retries_then_raises(self, client):
        resp = _make_response(500, text="server err")
        mock_client = _make_mock_client("get", side_effect=[resp, resp, resp])
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Cin7APIError):
                await client.invoke("GET", "Product")
        assert mock_client.get.await_count == 3

    async def test_5xx_retry_then_succeeds(self, client):
        resp_500 = _make_response(500)
        resp_200 = _make_response(200, {"ok": True})
        mock_client = _make_mock_client("get", side_effect=[resp_500, resp_200])
        with patch("httpx.AsyncClient", return_value=mock_client):
            status, body, _ = await client.invoke("GET", "Product")
        assert status == 200
        assert body == {"ok": True}

    async def test_400_returned_not_raised(self, client):
        """Bad request errors are data the model needs to see, not transport failures."""
        resp = _make_response(400, [{"Exception": "Invalid Sku format"}])
        mock_client = _make_mock_client("get", return_value=resp)
        with patch("httpx.AsyncClient", return_value=mock_client):
            status, body, _ = await client.invoke("GET", "Product", query_params={"Sku": "!@#"})
        assert status == 400
        assert body == [{"Exception": "Invalid Sku format"}]
        # No retry on 4xx
        assert mock_client.get.await_count == 1

    async def test_422_returned_not_raised(self, client):
        resp = _make_response(422, {"errors": ["validation failed"]})
        mock_client = _make_mock_client("post", return_value=resp)
        with patch("httpx.AsyncClient", return_value=mock_client):
            status, body, _ = await client.invoke("POST", "Sale", body={})
        assert status == 422

    async def test_network_error_retry_then_succeeds(self, client):
        import httpx
        resp_200 = _make_response(200, {})
        mock_client = _make_mock_client(
            "get", side_effect=[httpx.ConnectError("boom"), resp_200]
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            status, _, _ = await client.invoke("GET", "Product")
        assert status == 200
        assert mock_client.get.await_count == 2

    async def test_network_error_retries_exhausted(self, client):
        import httpx
        mock_client = _make_mock_client(
            "get",
            side_effect=[httpx.ConnectError("a"), httpx.ConnectError("b"), httpx.ConnectError("c")],
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Cin7APIError, match="Network error"):
                await client.invoke("GET", "Product")
        assert mock_client.get.await_count == 3

    async def test_non_json_body_returns_raw_string(self, client):
        """If the response body isn't JSON, body is returned as a {'raw': text} dict."""
        resp = _make_response(200, json_data=None, text="not json")
        mock_client = _make_mock_client("get", return_value=resp)
        with patch("httpx.AsyncClient", return_value=mock_client):
            status, body, _ = await client.invoke("GET", "Product")
        assert status == 200
        assert body == {"raw": "not json"}

    async def test_auth_headers_sent(self, client):
        resp = _make_response(200, {})
        mock_client = _make_mock_client("get", return_value=resp)
        with patch("httpx.AsyncClient", return_value=mock_client) as ctor:
            await client.invoke("GET", "Product")
        # Confirm AsyncClient was created with the right headers
        ctor_kwargs = ctor.call_args.kwargs
        headers = ctor_kwargs.get("headers", {})
        assert headers.get("api-auth-accountid") == "acct-123"
        assert headers.get("api-auth-applicationkey") == "key-abc"


def test_get_cin7_client_caches(monkeypatch):
    """The module-level get_cin7_client() returns the same instance."""
    from cin7_meta.utils import cin7_client as mod
    monkeypatch.setenv("CIN7_ACCOUNT_ID", "a")
    monkeypatch.setenv("CIN7_API_KEY", "k")
    monkeypatch.setattr(mod, "_client", None)
    c1 = mod.get_cin7_client()
    c2 = mod.get_cin7_client()
    assert c1 is c2
