"""Tests for the aqueduct bridge (clinical trials pipeline)."""

from __future__ import annotations

from numeraire.sources import aqueduct_bridge


def test_company_title(monkeypatch):
    """_company_title should look up the ticker from EDGAR tickers."""
    monkeypatch.setattr(aqueduct_bridge.edgar, "_tickers", lambda: {
        "0": {"ticker": "ABBV", "cik_str": 1800, "title": "AbbVie Inc."},
    })
    result = aqueduct_bridge._company_title("ABBV")
    assert result == "AbbVie Inc."


def test_company_title_unknown(monkeypatch):
    """Unknown ticker returns None."""
    monkeypatch.setattr(aqueduct_bridge.edgar, "_tickers", lambda: {})
    assert aqueduct_bridge._company_title("FAKE") is None


def test_match_token_extracts_first_significant():
    """_match_token strips stop words and returns the first remaining token."""
    result = aqueduct_bridge._match_token("AbbVie Inc.")
    assert result == "abbvie"


def test_match_token_ignores_stop_words():
    """Words in _STOP set should be excluded."""
    result = aqueduct_bridge._match_token("Pfizer Pharmaceuticals Inc")
    assert result == "pfizer"


def test_match_token_short_tokens():
    """Words <= 2 chars should be excluded."""
    result = aqueduct_bridge._match_token("AB Co Ltd")
    assert result is None


def test_match_token_strips_punctuation():
    result = aqueduct_bridge._match_token("Johnson & Johnson")
    assert result == "johnson"


def test_ingest_no_ticker(monkeypatch):
    """Unknown ticker returns empty result."""
    monkeypatch.setattr(aqueduct_bridge.edgar, "_tickers", lambda: {})
    result = aqueduct_bridge.ingest("FAKE")
    assert result == ("", 0, 0)


def test_ingest_no_title(monkeypatch):
    """Ticker with no title returns empty."""
    monkeypatch.setattr(aqueduct_bridge.edgar, "_tickers", lambda: {
        "0": {"ticker": "XOM", "cik_str": 34088, "title": "Exxon"}})
    # No match token for 'Exxon' (single token, no stop words removed)
    # Actually 'exxon' should match. Let's test with a short one:
    monkeypatch.setattr(aqueduct_bridge.edgar, "_tickers", lambda: {
        "0": {"ticker": "FOO", "cik_str": 1, "title": "AB Co"}})
    result = aqueduct_bridge.ingest("FOO")
    assert result == ("", 0, 0)
