"""Shared test fixtures for mcp-cin7-meta tests."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from cin7_meta.utils.spec_loader import load_spec_from_dict
from tests.fixtures.mini_spec import MINI_CATALOG

MODULE_ENDPOINTS = "cin7_meta.resources.endpoints"
MODULE_INVOKE = "cin7_meta.resources.invoke"
MODULE_ISSUES = "cin7_meta.resources.issues"


@pytest.fixture
def mini_spec_index():
    """A SpecIndex built from the hand-rolled MINI_CATALOG fixture."""
    return load_spec_from_dict(MINI_CATALOG)


@contextmanager
def _patch_spec(module_path: str):
    """Patch `get_spec` in a resource module to return the mini-fixture index."""
    import importlib

    idx = load_spec_from_dict(MINI_CATALOG)
    target = importlib.import_module(module_path)
    if hasattr(target, "get_spec"):
        with patch(f"{module_path}.get_spec", return_value=idx):
            yield idx
    else:
        yield idx


@pytest.fixture
def patch_spec():
    """Provide the patch_spec context manager as a fixture."""
    return _patch_spec


@contextmanager
def _mock_cin7(
    module_path: str,
    *,
    return_value: tuple | None = None,
    side_effect=None,
):
    """Patch `get_cin7_client` in a resource module and stub `invoke()`.

    `return_value` should be a `(status, body, headers)` tuple.
    """
    mock_client = AsyncMock()
    if side_effect is not None:
        mock_client.invoke.side_effect = side_effect
    else:
        mock_client.invoke.return_value = return_value
    with patch(f"{module_path}.get_cin7_client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_cin7():
    """Provide the mock_cin7 context manager as a fixture."""
    return _mock_cin7
