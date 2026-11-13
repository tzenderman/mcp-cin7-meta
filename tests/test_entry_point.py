"""Installers (Atrium) and `uvx --from git+...` launch this server through
console scripts the package installs into its venv's bin/ — never `python -m`.
The installed metadata must expose each one, resolving to the right main()."""

from importlib.metadata import entry_points

import pytest

from cin7_meta import server_stdio
from cin7_meta.cli import refresh_spec


def _load(name):
    (ep,) = entry_points(group="console_scripts", name=name)
    return ep.load()


def test_console_script_launches_stdio_server():
    # Kept for existing installs (Atrium) that launch `mcp-cin7-meta`.
    assert _load("mcp-cin7-meta") is server_stdio.main


def test_cin7_meta_stdio_script():
    assert _load("cin7-meta-stdio") is server_stdio.main


def test_cin7_meta_refresh_spec_script():
    assert _load("cin7-meta-refresh-spec") is refresh_spec.main


def test_cin7_meta_http_script(monkeypatch):
    # server_http builds the app at import; allow it without OAuth config.
    monkeypatch.setenv("MCP_ALLOW_NO_AUTH", "1")
    from cin7_meta import server_http

    assert _load("cin7-meta-http") is server_http.main
