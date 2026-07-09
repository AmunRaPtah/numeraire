"""Tests for S&P 500 survivorship-free membership parser."""

from __future__ import annotations

from numeraire.sources import sp500


def test_norm_ticker():
    assert sp500._norm_ticker("BRK.B") == "BRK-B"
    assert sp500._norm_ticker("BRK.B ") == "BRK-B"
    assert sp500._norm_ticker("") == ""
    assert sp500._norm_ticker("AAPL") == "AAPL"
    assert sp500._norm_ticker("BF.B") == "BF-B"


def test_parse_date_iso():
    assert sp500._parse_date("2023-06-01") == "2023-06-01"


def test_parse_date_long():
    assert sp500._parse_date("June 1, 2023") == "2023-06-01"
    assert sp500._parse_date("June 01, 2023") == "2023-06-01"


def test_parse_date_abbreviated():
    assert sp500._parse_date("Jun 1, 2023") == "2023-06-01"


def test_parse_date_none():
    assert sp500._parse_date(None) is None
    assert sp500._parse_date("") is None


def test_parse_date_extracted():
    assert sp500._parse_date("some text 2023-06-01 more") == "2023-06-01"


def test_find_tables_simple():
    html = (
        "<table><tr><th>Symbol</th><th>Date Added</th></tr><tr><td>AAPL</td><td>1982-01-01</td></tr></table>"
    )
    tables = sp500._find_tables(html)
    assert len(tables) == 1
    assert len(tables[0]) == 2  # header + 1 data row


def test_build_membership_current():
    """Test that current members are extracted."""
    html = (
        "<table><tr><th>Symbol</th><th>Security</th><th>Date added</th></tr>"
        "<tr><td>AAPL</td><td>Apple Inc.</td><td>1982-01-01</td></tr>"
        "<tr><td>MSFT</td><td>Microsoft Corp.</td><td>1994-06-01</td></tr>"
        "</table>"
    )
    tables = sp500._find_tables(html)
    rows = sp500._build_membership(tables)
    tickers = {r["ticker"] for r in rows}
    assert "AAPL" in tickers
    assert "MSFT" in tickers


def test_build_membership_empty():
    """No tables should produce empty list."""
    assert sp500._build_membership([]) == []
