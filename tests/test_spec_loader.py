"""Tests for the normalized spec loader and index."""

import json

import pytest

from cin7_meta.utils.spec_loader import (
    SpecIndex,
    load_spec_from_dict,
    load_spec_from_path,
)
from tests.fixtures.mini_spec import MINI_CATALOG


@pytest.fixture
def spec():
    return load_spec_from_dict(MINI_CATALOG)


def test_load_returns_spec_index(spec):
    assert isinstance(spec, SpecIndex)
    assert spec.base_url == "https://example.test/v2/"


def test_endpoints_by_key_uppercase_method(spec):
    assert "GET Product" in spec.endpoints_by_key
    assert "POST Product" in spec.endpoints_by_key
    assert "GET Sale" in spec.endpoints_by_key
    assert "GET saleList" in spec.endpoints_by_key


def test_get_endpoint_normalizes_method_case(spec):
    assert spec.get_endpoint("get", "Product") is not None
    assert spec.get_endpoint("GET", "Product") is not None
    assert spec.get_endpoint("Get", "Product") is not None


def test_get_endpoint_strips_leading_slash(spec):
    a = spec.get_endpoint("GET", "/Product")
    b = spec.get_endpoint("GET", "Product")
    assert a is b


def test_get_endpoint_returns_none_for_unknown(spec):
    assert spec.get_endpoint("GET", "nope") is None
    assert spec.get_endpoint("DELETE", "Product") is None


def test_search_entries_include_one_per_endpoint(spec):
    methods_paths = {(e.method, e.path) for e in spec.search_entries}
    assert ("GET", "Product") in methods_paths
    assert ("POST", "Product") in methods_paths
    assert ("GET", "Sale") in methods_paths
    assert ("GET", "saleList") in methods_paths


def test_endpoint_def_fields(spec):
    e = spec.get_endpoint("GET", "Product")
    assert e.method == "GET"
    assert e.path == "Product"
    assert e.group == "Product"
    assert e.summary == "List products"
    assert len(e.query_params) == 3
    page = e.query_params[0]
    assert page.name == "Page"
    assert page.type == "integer"
    assert page.required is False
    assert page.default == 1


def test_required_param_flag_preserved(spec):
    sale = spec.get_endpoint("GET", "Sale")
    id_param = sale.query_params[0]
    assert id_param.required is True


def test_load_from_path_round_trip(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(MINI_CATALOG))
    spec = load_spec_from_path(str(path))
    assert isinstance(spec, SpecIndex)
    assert len(spec.endpoints_by_key) == 4


def test_load_from_path_missing_raises(tmp_path):
    path = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        load_spec_from_path(str(path))


def test_load_from_path_malformed_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    with pytest.raises(ValueError):
        load_spec_from_path(str(path))


def test_load_from_dict_missing_endpoints_raises():
    with pytest.raises(ValueError):
        load_spec_from_dict({"base_url": "x"})


def test_get_spec_uses_env_path(monkeypatch, tmp_path):
    """The cached `get_spec()` reads CIN7_SPEC_PATH when set."""
    from cin7_meta.utils import spec_loader as mod

    path = tmp_path / "spec.json"
    path.write_text(json.dumps(MINI_CATALOG))
    monkeypatch.setenv("CIN7_SPEC_PATH", str(path))
    monkeypatch.setattr(mod, "_spec", None)
    spec = mod.get_spec()
    assert isinstance(spec, SpecIndex)
    # Cached on subsequent calls
    assert mod.get_spec() is spec


def test_real_vendored_spec_loads():
    """Smoke test against the vendored cin7_v2.json shipped in the repo."""
    from cin7_meta.utils import spec_loader as mod

    mod._spec = None  # reset cache
    spec = mod.get_spec()
    assert isinstance(spec, SpecIndex)
    # We expect a couple hundred endpoints from the real Apiary spec
    assert len(spec.endpoints_by_key) > 100
    # A spot-check endpoint that's definitely real (Cin7 uses lowercase /product)
    assert spec.get_endpoint("GET", "product") is not None
    assert spec.get_endpoint("POST", "product") is not None


# --- Spec path resolution: CIN7_SPEC_PATH (file) > CIN7_SPEC_DIR (dir) > packaged ---


@pytest.fixture
def clean_spec_env(monkeypatch):
    monkeypatch.delenv("CIN7_SPEC_PATH", raising=False)
    monkeypatch.delenv("CIN7_SPEC_DIR", raising=False)
    return monkeypatch


def test_resolve_uses_packaged_spec_when_no_env(clean_spec_env):
    from cin7_meta.utils.spec_loader import DEFAULT_SPEC_PATH, resolve_spec_path

    assert resolve_spec_path() == DEFAULT_SPEC_PATH


def test_resolve_prefers_spec_dir_when_file_present(clean_spec_env, tmp_path):
    from cin7_meta.utils.spec_loader import SPEC_FILENAME, resolve_spec_path

    (tmp_path / SPEC_FILENAME).write_text(json.dumps(MINI_CATALOG))
    clean_spec_env.setenv("CIN7_SPEC_DIR", str(tmp_path))
    assert resolve_spec_path() == tmp_path / SPEC_FILENAME


def test_resolve_expands_user_in_spec_dir(clean_spec_env, tmp_path):
    from cin7_meta.utils.spec_loader import SPEC_FILENAME, resolve_spec_path

    (tmp_path / "s").mkdir()
    (tmp_path / "s" / SPEC_FILENAME).write_text(json.dumps(MINI_CATALOG))
    clean_spec_env.setenv("HOME", str(tmp_path))
    clean_spec_env.setenv("CIN7_SPEC_DIR", "~/s")
    assert resolve_spec_path() == tmp_path / "s" / SPEC_FILENAME


def test_resolve_falls_back_to_packaged_when_spec_dir_empty(clean_spec_env, tmp_path):
    from cin7_meta.utils.spec_loader import DEFAULT_SPEC_PATH, resolve_spec_path

    clean_spec_env.setenv("CIN7_SPEC_DIR", str(tmp_path))
    assert resolve_spec_path() == DEFAULT_SPEC_PATH


def test_resolve_explicit_spec_path_wins_over_spec_dir(clean_spec_env, tmp_path):
    from cin7_meta.utils.spec_loader import SPEC_FILENAME, resolve_spec_path

    (tmp_path / SPEC_FILENAME).write_text(json.dumps(MINI_CATALOG))
    explicit = tmp_path / "pinned.json"
    explicit.write_text(json.dumps(MINI_CATALOG))
    clean_spec_env.setenv("CIN7_SPEC_DIR", str(tmp_path))
    clean_spec_env.setenv("CIN7_SPEC_PATH", str(explicit))
    assert resolve_spec_path() == explicit


def test_resolve_error_names_checked_paths_and_refresh_command(clean_spec_env, tmp_path):
    from cin7_meta.utils import spec_loader as mod

    missing_pkg = tmp_path / "pkg" / mod.SPEC_FILENAME
    clean_spec_env.setattr(mod, "DEFAULT_SPEC_PATH", missing_pkg)
    clean_spec_env.setenv("CIN7_SPEC_DIR", str(tmp_path / "dir"))

    with pytest.raises(FileNotFoundError) as exc:
        mod.resolve_spec_path()
    msg = str(exc.value)
    assert str(tmp_path / "dir" / mod.SPEC_FILENAME) in msg
    assert str(missing_pkg) in msg
    assert "cin7-meta-refresh-spec" in msg


def test_get_spec_reads_from_spec_dir(clean_spec_env, tmp_path):
    from cin7_meta.utils import spec_loader as mod

    (tmp_path / mod.SPEC_FILENAME).write_text(json.dumps(MINI_CATALOG))
    clean_spec_env.setenv("CIN7_SPEC_DIR", str(tmp_path))
    clean_spec_env.setattr(mod, "_spec", None)
    assert len(mod.get_spec().endpoints_by_key) == 4
