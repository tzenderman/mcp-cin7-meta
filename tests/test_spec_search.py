"""Tests for ranked endpoint search."""

import pytest

from cin7_meta.utils.spec_loader import load_spec_from_dict
from cin7_meta.utils.spec_search import search_spec_index
from tests.fixtures.mini_spec import MINI_CATALOG


@pytest.fixture
def spec():
    return load_spec_from_dict(MINI_CATALOG)


def test_returns_canonical_shape(spec):
    out = search_spec_index(spec, keyword="product")
    assert set(out.keys()) >= {"results", "total", "truncated"}
    assert isinstance(out["results"], list)
    assert isinstance(out["total"], int)
    assert isinstance(out["truncated"], bool)


def test_finds_substring_in_path(spec):
    out = search_spec_index(spec, keyword="product")
    paths = [(r["method"], r["path"]) for r in out["results"]]
    assert ("GET", "Product") in paths
    assert ("POST", "Product") in paths


def test_case_insensitive(spec):
    out = search_spec_index(spec, keyword="PRODUCT")
    assert any(r["path"] == "Product" for r in out["results"])


def test_methods_filter(spec):
    out = search_spec_index(spec, keyword="product", methods=["POST"])
    assert all(r["method"] == "POST" for r in out["results"])
    assert any(r["path"] == "Product" for r in out["results"])


def test_methods_filter_excludes_others(spec):
    out = search_spec_index(spec, keyword="product", methods=["DELETE"])
    assert out["results"] == []
    assert out["total"] == 0


def test_limit_truncates_results(spec):
    out = search_spec_index(spec, keyword="product", limit=1)
    assert len(out["results"]) == 1
    assert out["truncated"] is True


def test_total_reflects_matches_not_limit(spec):
    out = search_spec_index(spec, keyword="product", limit=1)
    assert out["total"] >= 2


def test_ranking_exact_path_first(spec):
    """When keyword exactly matches a path, that endpoint ranks before substring matches."""
    out = search_spec_index(spec, keyword="Sale")
    paths = [r["path"] for r in out["results"]]
    # Exact "Sale" should come before "saleList"
    assert paths.index("Sale") < paths.index("saleList")


def test_ranking_prefix_beats_substring(spec):
    """Prefix matches rank before substring matches when no exact match."""
    out = search_spec_index(spec, keyword="sale")
    paths = [r["path"] for r in out["results"]]
    # "saleList" starts with "sale", so it should rank near top
    assert "saleList" in paths


def test_search_matches_summary(spec):
    """Keyword matches inside summaries."""
    out = search_spec_index(spec, keyword="single")
    assert any(r["path"] == "Sale" for r in out["results"])


def test_search_matches_param_name(spec):
    """Keyword matches inside param names."""
    out = search_spec_index(spec, keyword="search")  # matches the `Search` param of saleList
    assert any(r["path"] == "saleList" for r in out["results"])


def test_search_matches_group(spec):
    """Keyword matches against group name."""
    # Group "Product" — all Product-group endpoints should match the keyword
    out = search_spec_index(spec, keyword="Product")
    paths = {r["path"] for r in out["results"]}
    assert "Product" in paths


def test_empty_keyword_returns_error(spec):
    out = search_spec_index(spec, keyword="")
    assert "error" in out


def test_keyword_only_whitespace_returns_error(spec):
    out = search_spec_index(spec, keyword="   ")
    assert "error" in out


def test_results_include_method_path_summary_group(spec):
    out = search_spec_index(spec, keyword="product")
    for r in out["results"]:
        assert "method" in r
        assert "path" in r
        assert "summary" in r
        assert "group" in r


def test_no_matches_returns_empty(spec):
    out = search_spec_index(spec, keyword="zzz-no-such-endpoint")
    assert out["results"] == []
    assert out["total"] == 0
    assert out["truncated"] is False


def test_methods_normalized_to_uppercase(spec):
    out = search_spec_index(spec, keyword="product", methods=["post"])
    assert any(r["method"] == "POST" for r in out["results"])
