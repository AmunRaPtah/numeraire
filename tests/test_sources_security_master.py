"""Tests for the security master sponsor-name -> CIK/ticker resolver (ADR-4)."""

from __future__ import annotations

from numeraire.sources import security_master


def test_normalize_strips_corporate_suffixes():
    assert security_master.normalize("AbbVie Inc.") == "abbvie"
    assert security_master.normalize("Johnson & Johnson") == "johnson johnson"
    assert security_master.normalize("Eli Lilly and Company") == "eli lilly"


def test_normalize_empty():
    assert security_master.normalize("") == ""
    assert security_master.normalize(None) == ""


def _idx():
    tickers = {
        "0": {"ticker": "ABBV", "cik_str": 1800, "title": "AbbVie Inc."},
        "1": {"ticker": "MRNA", "cik_str": 1682852, "title": "Moderna, Inc."},
        "2": {"ticker": "VRTX", "cik_str": 875320, "title": "Vertex Pharmaceuticals Inc"},
    }
    return {
        security_master.normalize(r["title"]): (r["cik_str"], r["ticker"]) for r in tickers.values()
    }


def test_resolve_exact_normalized_match():
    idx = _idx()
    assert security_master.resolve("AbbVie Inc.", idx) == (1800, "ABBV")


def test_resolve_contained_name_fallback():
    """'ModernaTX, Inc.' (a real CT.gov lead sponsor) should resolve via 'Moderna, Inc.' in the index."""
    idx = _idx()
    assert security_master.resolve("ModernaTX, Inc.", idx) == (1682852, "MRNA")


def test_resolve_no_match_returns_none():
    idx = _idx()
    assert security_master.resolve("Yale University", idx) is None


def test_resolve_empty_sponsor_returns_none():
    idx = _idx()
    assert security_master.resolve("", idx) is None
    assert security_master.resolve(None, idx) is None


def test_resolve_avoids_short_token_false_positive():
    """A short, unrelated sponsor name should not spuriously match via startswith."""
    idx = _idx()
    # "Vertex" alone is 6 chars (>=4) and is a real prefix match, so it should resolve...
    assert security_master.resolve("Vertex", idx) == (875320, "VRTX")
    # ...but a short unrelated name should not match anything in the index.
    assert security_master.resolve("Vx", idx) is None
