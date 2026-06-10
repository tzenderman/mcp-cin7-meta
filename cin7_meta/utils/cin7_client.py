"""Async Cin7 Core REST client with retry logic.

Ported from `mcp-cin7-core/cin7_core_server/cin7_client.py` and trimmed to a
single generic `invoke(method, path, query_params, body)` entry point.

The client is single-tenant: credentials come from `CIN7_ACCOUNT_ID` and
`CIN7_API_KEY`. Optional `CIN7_BASE_URL` overrides the default
`https://inventory.dearsystems.com/ExternalApi/v2/`.

Transport-level failures raise the `Cin7*Error` hierarchy; HTTP 4xx errors
that represent valid API responses (400 bad request, 422 unprocessable) are
returned as data so the model can see them and self-correct.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

from .errors import (
    Cin7APIError,
    Cin7AuthError,
    Cin7NotFoundError,
    Cin7RateLimitError,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://inventory.dearsystems.com/ExternalApi/v2/"
MAX_RETRIES = 3
DEFAULT_RETRY_DELAYS = [1.0, 2.0, 4.0]


class Cin7Client:
    """Minimal async client for the Cin7 Core REST API.

    Uses a per-request `httpx.AsyncClient` with automatic retry on 429/5xx and
    network errors. The only public method is `invoke()`.
    """

    def __init__(self, base_url: str, account_id: str, application_key: str):
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        self.base_url = base_url
        self.account_id = account_id
        self.application_key = application_key
        self.max_retries = MAX_RETRIES
        self.retry_delays = list(DEFAULT_RETRY_DELAYS)

    @classmethod
    def from_env(cls) -> "Cin7Client":
        """Build a client from environment variables.

        Required: `CIN7_ACCOUNT_ID`, `CIN7_API_KEY`.
        Optional: `CIN7_BASE_URL` (defaults to the public Cin7 v2 URL).

        Raises `Cin7AuthError` if credentials are missing.
        """
        account_id = os.getenv("CIN7_ACCOUNT_ID")
        application_key = os.getenv("CIN7_API_KEY")
        base_url = os.getenv("CIN7_BASE_URL", DEFAULT_BASE_URL)

        if not account_id or not application_key:
            raise Cin7AuthError(
                "Missing CIN7_ACCOUNT_ID or CIN7_API_KEY in environment."
            )

        return cls(base_url=base_url, account_id=account_id, application_key=application_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-auth-accountid": self.account_id,
            "api-auth-applicationkey": self.application_key,
        }

    async def invoke(
        self,
        method: str,
        path: str,
        query_params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        """Execute a Cin7 Core API call with retry on 429/5xx.

        Args:
            method: HTTP verb. Case-insensitive.
            path: Endpoint path (relative to `base_url`). Leading `/` is stripped.
            query_params: Query-string parameters.
            body: JSON request body.

        Returns:
            `(status_code, parsed_body, response_headers)`. `parsed_body` is the
            JSON-decoded response when possible, `{"raw": text}` when the body
            is not valid JSON, or `None` when there is no body.

        Raises:
            Cin7AuthError: HTTP 401.
            Cin7NotFoundError: HTTP 404.
            Cin7RateLimitError: HTTP 429 after retries exhausted.
            Cin7APIError: HTTP 5xx after retries, network failures, etc.
        """
        method_lower = method.lower()
        normalized_path = path.lstrip("/")

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=httpx.Timeout(60.0, connect=10.0),
        ) as client:
            response = await self._execute_with_retry(
                client, method_lower, normalized_path, query_params, body
            )

        status = response.status_code
        headers = dict(response.headers)

        # 401 / 404 are transport-level failures the model can't fix by adjusting the body.
        if status == 401:
            raise Cin7AuthError(
                "Invalid Cin7 credentials. Check CIN7_ACCOUNT_ID and CIN7_API_KEY."
            )
        if status == 404:
            raise Cin7NotFoundError(f"Cin7 endpoint not found: {method.upper()} {normalized_path}")

        try:
            parsed = response.json()
        except (ValueError, httpx.DecodingError):
            text = response.text or ""
            parsed = {"raw": text} if text else None

        return status, parsed, headers

    async def _execute_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        query_params: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> httpx.Response:
        kwargs: dict[str, Any] = {}
        if query_params is not None:
            kwargs["params"] = query_params
        if body is not None:
            kwargs["json"] = body

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                start = time.perf_counter()
                response = await getattr(client, method)(path, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                logger.debug(
                    "HTTP %s %s status=%s elapsed_ms=%.2f",
                    method.upper(),
                    path,
                    response.status_code,
                    elapsed_ms,
                )

                if response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delays[attempt])
                        continue
                    raise Cin7RateLimitError(
                        f"Rate limit exceeded after {self.max_retries} retries"
                    )

                if response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delays[attempt])
                        continue
                    raise Cin7APIError(
                        f"Server error {response.status_code} after {self.max_retries} retries"
                    )

                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delays[attempt])
                    continue

        raise Cin7APIError(
            f"Network error after {self.max_retries} retries: {last_error}"
        )


_client: Cin7Client | None = None


def get_cin7_client() -> Cin7Client:
    """Return the cached process-wide `Cin7Client`, building it on first call."""
    global _client
    if _client is None:
        _client = Cin7Client.from_env()
    return _client
