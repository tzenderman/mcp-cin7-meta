"""Tests for the packaged spec-refresh command (`cin7-meta-refresh-spec`).

No network: `fetch_apib` is monkeypatched to return the mini API Blueprint.
"""

import json

import pytest

from cin7_meta.cli import refresh_spec as cli
from tests.fixtures.mini_apib import MINI_APIB


@pytest.fixture
def no_network(monkeypatch):
    def _fail():
        raise AssertionError("network fetch attempted")

    monkeypatch.setattr(cli, "fetch_apib", _fail)
    return monkeypatch


def test_output_dir_defaults_to_package_spec_dir(monkeypatch):
    from cin7_meta.utils.spec_loader import SPEC_DIR

    monkeypatch.delenv("CIN7_SPEC_DIR", raising=False)
    assert cli.output_dir() == SPEC_DIR


def test_output_dir_uses_spec_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CIN7_SPEC_DIR", str(tmp_path / "s"))
    assert cli.output_dir() == tmp_path / "s"


def test_refresh_writes_apib_and_catalog_to_spec_dir(no_network, tmp_path):
    out = tmp_path / "nested" / "spec"
    no_network.setenv("CIN7_SPEC_DIR", str(out))
    no_network.setattr(cli, "fetch_apib", lambda: MINI_APIB)

    assert cli.main([]) == 0

    assert (out / "cin7_v2.apib").read_text() == MINI_APIB
    catalog = json.loads((out / "cin7_v2.json").read_text())
    assert catalog["endpoints"]
    assert catalog["source"] == cli.SOURCE_URL
    assert "generated_at" in catalog


def test_refreshed_spec_dir_is_what_the_loader_reads(no_network, tmp_path):
    from cin7_meta.utils import spec_loader

    no_network.setenv("CIN7_SPEC_DIR", str(tmp_path))
    no_network.delenv("CIN7_SPEC_PATH", raising=False)
    no_network.setattr(cli, "fetch_apib", lambda: MINI_APIB)
    cli.main([])

    assert spec_loader.resolve_spec_path() == tmp_path / "cin7_v2.json"


def test_no_fetch_reparses_existing_apib_in_spec_dir(no_network, tmp_path):
    no_network.setenv("CIN7_SPEC_DIR", str(tmp_path))
    (tmp_path / "cin7_v2.apib").write_text(MINI_APIB)

    assert cli.main(["--no-fetch"]) == 0
    assert json.loads((tmp_path / "cin7_v2.json").read_text())["endpoints"]


def test_no_fetch_without_apib_raises(no_network, tmp_path):
    no_network.setenv("CIN7_SPEC_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        cli.main(["--no-fetch"])


def test_scripts_wrapper_delegates_to_package_cli():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "scripts" / "refresh_spec.py"
    spec = importlib.util.spec_from_file_location("_refresh_wrapper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main is cli.main
